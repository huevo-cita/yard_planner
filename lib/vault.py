"""Encrypted yard bundles, so personal data can travel in a public repo.

    python3 -m lib.vault lock <slug>       encrypt a yard into vault/<slug>.tar.gz.enc
    python3 -m lib.vault unlock <slug>     restore it from the vault
    python3 -m lib.vault list              what is in the vault, and how stale
    python3 -m lib.vault lock --all        every yard on this machine

Why this exists
---------------
A yard record is the most identifying kind of file a person can write. It holds
a street address, a latitude and longitude accurate to a rooftop, a parcel
number that ties the property to a name in a public land registry, and a profile
naming who lives there, when they are away, and what they can afford to spend.
`.gitignore` keeps all of that out of the repo, which solves the leak and
creates a new problem: the system cannot then be run anywhere else, because the
code without the data draws nothing.

This closes that. One yard becomes one encrypted file that is safe to commit.

What it is
----------
AES-256-CBC with a key stretched from a passphrase by PBKDF2-HMAC-SHA256 at
600,000 iterations, over a random salt, through the `openssl` binary that ships
with macOS and every Linux distribution. No dependency to install, on any
machine, which is the whole point of a portability tool.

Two things that are true and worth saying plainly:

- CBC gives confidentiality, not authenticity. Someone who can write to the repo
  could corrupt a bundle, and the decryption would fail loudly rather than
  silently hand back altered data — but this is not an authenticated cipher and
  should not be used as if it were. For a single author's own backup that is an
  acceptable trade. For anything adversarial, use age or GPG instead.
- The passphrase is the entire security of the scheme. A short one is a
  formality: 600,000 iterations only multiplies the attacker's cost per guess,
  and a public repo means unlimited offline guesses. Use a long passphrase.

The passphrase is read from the `YARD_VAULT_PASSPHRASE` environment variable, or
prompted for. It is never written to disk and never passed as a command-line
argument, where it would be visible to every other process on the machine via
`ps`; it goes to openssl through a file descriptor instead.
"""

import argparse
import datetime
import getpass
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile

from . import yards

# The vault belongs to the repo, not to the data. It is the thing that gets
# committed, so it has to sit in the checkout even when the yards live elsewhere.
VAULT = os.path.join(yards.REPO_ROOT, "vault")
ITER = 600_000
MANIFEST = "manifest.json"

# Nothing derived, nothing enormous, nothing a re-run cannot rebuild.
SKIP_DIRS = {"__pycache__", ".cache"}
SKIP_SUFFIX = (".pyc",)


def _openssl():
    exe = shutil.which("openssl")
    if not exe:
        raise SystemExit(
            "openssl is not on PATH. It ships with macOS and every Linux "
            "distribution; on Windows use WSL or install Git for Windows, "
            "which bundles it.")
    return exe


def passphrase(confirm=False):
    env = os.environ.get("YARD_VAULT_PASSPHRASE")
    if env:
        return env
    if not sys.stdin.isatty():
        raise SystemExit(
            "no passphrase: set YARD_VAULT_PASSPHRASE, or run this "
            "interactively so it can be typed.")
    p = getpass.getpass("vault passphrase: ")
    if confirm:
        if p != getpass.getpass("again: "):
            raise SystemExit("the two did not match.")
        if len(p) < 12:
            raise SystemExit(
                "that passphrase is too short to protect a file published on "
                "the internet. Use at least 12 characters, and prefer a long "
                "phrase over a short complicated one.")
    return p


def _run(args, pw, data_in=None):
    """Call openssl with the passphrase on a pipe rather than the command line.

    `-pass fd:N` keeps it out of `ps` output and out of the shell history.
    """
    r_fd, w_fd = os.pipe()
    os.write(w_fd, pw.encode() + b"\n")
    os.close(w_fd)
    try:
        return subprocess.run(args + ["-pass", f"fd:{r_fd}"], input=data_in,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              pass_fds=(r_fd,), check=False)
    finally:
        os.close(r_fd)


def _filter(info):
    parts = info.name.split("/")
    if any(p in SKIP_DIRS for p in parts):
        return None
    if info.name.endswith(SKIP_SUFFIX):
        return None
    return info


def lock(slug, pw=None):
    """Encrypt one yard directory into vault/<slug>.tar.gz.enc."""
    src = yards.yard_dir(slug)
    if not os.path.isdir(src):
        raise SystemExit(f"no yard directory at {src}")
    pw = pw or passphrase(confirm=True)
    os.makedirs(VAULT, exist_ok=True)

    tmp = tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False)
    tmp.close()
    try:
        with tarfile.open(tmp.name, "w:gz") as tar:
            tar.add(src, arcname=slug, filter=_filter)
        size = os.path.getsize(tmp.name)
        with open(tmp.name, "rb") as fh:
            blob = fh.read()
    finally:
        os.unlink(tmp.name)

    out = os.path.join(VAULT, f"{slug}.tar.gz.enc")
    r = _run([_openssl(), "enc", "-aes-256-cbc", "-pbkdf2", "-iter", str(ITER),
              "-salt", "-md", "sha256"], pw, data_in=blob)
    if r.returncode != 0:
        raise SystemExit("openssl failed: " + r.stderr.decode().strip())
    with open(out, "wb") as fh:
        fh.write(r.stdout)

    _write_manifest(slug, size, len(r.stdout))
    print(f"locked {slug}: {size / 1024:.0f} KB of yard data -> "
          f"{len(r.stdout) / 1024:.0f} KB at vault/{slug}.tar.gz.enc")
    print("  safe to commit. The passphrase is the only thing protecting it, "
          "so it does not go in the repo, in a note beside the repo, or in a "
          "chat window.")
    return out


def unlock(slug, pw=None, force=False):
    """Restore one yard directory from the vault."""
    enc = os.path.join(VAULT, f"{slug}.tar.gz.enc")
    if not os.path.exists(enc):
        raise SystemExit(f"nothing in the vault for {slug!r}. "
                         f"`python3 -m lib.vault list` shows what is there.")
    dest = yards.yard_dir(slug)
    if os.path.isdir(dest) and not force:
        raise SystemExit(
            f"{dest} already exists. Restoring would overwrite local work that "
            f"may be newer than the bundle. Move it aside, or pass --force if "
            f"you are sure the bundle is the better copy.")
    pw = pw or passphrase()

    with open(enc, "rb") as fh:
        blob = fh.read()
    r = _run([_openssl(), "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter",
              str(ITER), "-md", "sha256"], pw, data_in=blob)
    if r.returncode != 0:
        err = r.stderr.decode().strip()
        if "bad decrypt" in err or "BAD_DECRYPT" in err:
            raise SystemExit("wrong passphrase, or the bundle is damaged.")
        raise SystemExit("openssl failed: " + err)

    tmp = tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False)
    try:
        tmp.write(r.stdout)
        tmp.close()
        with tarfile.open(tmp.name, "r:gz") as tar:
            _safe_extract(tar, yards.GARDEN_ROOT)
    finally:
        os.unlink(tmp.name)
    print(f"unlocked {slug} into {dest}")
    return dest


def _safe_extract(tar, root):
    """Extract, refusing any member that would land outside the root.

    A tar can name `../../.ssh/authorized_keys`. This bundle is one you wrote
    yourself, but it arrives over a network from a public host, and unpacking a
    downloaded archive without this check is how that stops being true.
    """
    root = os.path.realpath(root)
    for m in tar.getmembers():
        target = os.path.realpath(os.path.join(root, m.name))
        if not (target == root or target.startswith(root + os.sep)):
            raise SystemExit(f"refusing to extract {m.name!r}: it points "
                             f"outside {root}")
        if m.issym() or m.islnk():
            raise SystemExit(f"refusing to extract link {m.name!r}")
    tar.extractall(root)


def _write_manifest(slug, plain_bytes, enc_bytes):
    """What is in the vault, without saying anything about what is inside it.

    Deliberately no address, no coordinates, no file listing — this file is
    committed in the clear, and a manifest that named the streets would undo
    the encryption it is describing.
    """
    path = os.path.join(VAULT, MANIFEST)
    man = {}
    if os.path.exists(path):
        with open(path) as fh:
            man = json.load(fh)
    man[slug] = {"locked": datetime.date.today().isoformat(),
                 "plaintext_kb": round(plain_bytes / 1024, 1),
                 "encrypted_kb": round(enc_bytes / 1024, 1),
                 "cipher": f"aes-256-cbc, pbkdf2-sha256 x{ITER}"}
    with open(path, "w") as fh:
        json.dump(man, fh, indent=2, sort_keys=True)
        fh.write("\n")


def listing():
    man = {}
    path = os.path.join(VAULT, MANIFEST)
    if os.path.exists(path):
        with open(path) as fh:
            man = json.load(fh)
    slugs = sorted(set(list(man) + [
        f[:-len(".tar.gz.enc")] for f in os.listdir(VAULT)
        if f.endswith(".tar.gz.enc")] if os.path.isdir(VAULT) else []))
    if not slugs:
        print("the vault is empty. `python3 -m lib.vault lock <slug>` fills it.")
        return
    today = datetime.date.today()
    print(f"{'yard':<24} {'locked':<12} {'size':>9}   local copy")
    for s in slugs:
        m = man.get(s, {})
        when = m.get("locked", "?")
        try:
            age = (today - datetime.date.fromisoformat(when)).days
            when = f"{when} ({age}d)" if age else f"{when} (today)"
        except ValueError:
            pass
        size = m.get("encrypted_kb")
        here = "yes" if os.path.isdir(yards.yard_dir(s)) else "no"
        print(f"{s:<24} {when:<12} {size or '?':>7} KB   {here}")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    lk = sub.add_parser("lock", help="encrypt a yard into the vault")
    lk.add_argument("slug", nargs="?")
    lk.add_argument("--all", action="store_true", help="every yard found")

    ul = sub.add_parser("unlock", help="restore a yard from the vault")
    ul.add_argument("slug", nargs="?")
    ul.add_argument("--all", action="store_true")
    ul.add_argument("--force", action="store_true",
                    help="overwrite a local yard directory that already exists")

    sub.add_parser("list", help="what is in the vault")
    args = ap.parse_args()

    if args.cmd == "list":
        return listing()

    if args.cmd == "lock":
        slugs = list(yards.list_yards()) if args.all \
            else ([args.slug] if args.slug else [])
        if not slugs:
            raise SystemExit("name a yard, or pass --all")
        pw = passphrase(confirm=True)
        for s in slugs:
            lock(s, pw)
        return

    if args.cmd == "unlock":
        if args.all:
            slugs = sorted(f[:-len(".tar.gz.enc")]
                           for f in os.listdir(VAULT)
                           if f.endswith(".tar.gz.enc")) \
                if os.path.isdir(VAULT) else []
        else:
            slugs = [args.slug] if args.slug else []
        if not slugs:
            raise SystemExit("name a yard, or pass --all")
        pw = passphrase()
        for s in slugs:
            unlock(s, pw, force=args.force)


if __name__ == "__main__":
    main()
