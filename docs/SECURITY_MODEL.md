# Security model

## Goals

SaveDelta should be safe to run on an untrusted save folder when the operator
uses default limits. Safety means:

- no execution of input-controlled code;
- no writes to analyzed inputs;
- no archive extraction;
- bounded memory and parser work;
- no accidental path traversal;
- no active content in generated HTML;
- clear behavior when an analyzer cannot finish.

## Trust boundaries

| Boundary | Treatment |
|---|---|
| File and directory paths | Resolved locally; unreadable files become warnings |
| Symlinks | Skipped by default |
| Snapshot logical paths | Rejected when absolute, empty, or containing `..` |
| Snapshot ZIP members | Generated names only; size and SHA-256 checked against manifest |
| Generic ZIP entries | Inspected in memory; never extracted |
| SQLite | Copied to a temporary file, opened immutable/query-only |
| Text and structured values | Escaped in HTML; bounded in reports |
| Binary content | Read only under `--max-file-bytes` |

## Archive defenses

Snapshot manifests are capped at 16 MiB and one million entries. Every snapshot
member is streamed through SHA-256 verification before its manifest digest is
trusted, and it is verified again when read to detect a changed archive.
Generic ZIP
analysis defaults to 20,000 entries and 512 MiB total uncompressed size. Deep
member analysis is limited to 2 MiB per member and 20 changed members.
Encrypted members are metadata-only.

Python maintenance releases added additional overlap checks for malicious ZIP
structures; SaveDelta supports maintained Python 3.11+ versions and layers its
own limits on top.

## HTML output

The HTML report:

- escapes every file path, value, warning, and diff line;
- contains no JavaScript;
- loads no external stylesheet, font, image, or analytics endpoint;
- uses `default-src 'none'` with only inline style allowed;
- remains a single portable file.

## Non-goals

SaveDelta is not a malware sandbox, antivirus scanner, anti-cheat bypass, or
cryptographic format breaker. High entropy can suggest compressed or encrypted
data, but the tool does not attempt to defeat encryption.

It does not modify saves in v0.1.0. Future patch export must require explicit
operator intent, an automatic backup, precondition hashes, and post-write
verification.

## Responsible use

Only analyze files you are allowed to inspect. Do not publish proprietary game
assets, personal data, authentication tokens, or copyrighted save content in
issues. Reproduce bugs with the built-in synthetic demo whenever possible.
