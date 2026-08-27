# vault

Encrypted yard data. `*.tar.gz.enc` files here are safe to commit; everything
they contain is not.

```bash
yard vault lock <slug>       # encrypt a yard from the working tree into here
yard vault unlock <slug>     # restore it on another machine
yard vault list              # what is here, when it was locked, and how stale
```

AES-256-CBC with a key stretched by PBKDF2-HMAC-SHA256 at 600,000 iterations
over a random salt, via the `openssl` binary. See the "vault" section of the
top-level README for what that does and does not protect against, and
`lib/vault.py` for the implementation.

`manifest.json` is committed in the clear and says only which slugs exist, when
each was locked, and how large it is. It names no street and no coordinate,
because a manifest that did would undo the encryption it describes.

The plaintext tarball is written to a temporary file and deleted; `.gitignore`
also excludes `vault/*.tar.gz` so a stray one can never be committed.

**A bundle here is only as private as the passphrase.** It does not belong in
this repo, in a file beside this repo, or in a chat window.
