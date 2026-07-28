# Support

- Usage questions: open a GitHub Discussion.
- Reproducible bugs: use the bug report issue form.
- Feature ideas: use the feature request issue form.
- Security problems: follow `SECURITY.md`; do not file a public issue.

Before reporting a bug, run:

```bash
savedelta --version
savedelta inspect PATH --format json
python -m unittest discover -s tests -v
```

Remove personal paths and sensitive values from any shared output.
