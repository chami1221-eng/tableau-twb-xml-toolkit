# Contributing

Thank you for your interest in contributing to the Tableau TWB XML Toolkit.

## How to Contribute

### Reporting Issues

- Use [GitHub Issues](https://github.com/chami1221-eng/tableau-twb-xml-toolkit/issues) to report bugs or suggest features
- Include your Tableau version and the TWB XML snippet that caused the issue

### Adding XML Patterns

The pattern catalog (`docs/twb-patterns.md`) is the core asset of this project. To add a new pattern:

1. Fork this repository
2. Extract the pattern from a working TWB (Tableau Desktop or Cloud)
3. Validate against the XSD schema:
   ```bash
   python tools/publish_test.py your_workbook.twb --xsd
   ```
4. Add the pattern to `docs/twb-patterns.md` with:
   - Pattern name and category
   - Minimal XML snippet
   - Which Tableau version it was tested on
5. Submit a Pull Request

### Correction Records

If you discover a new pitfall in TWB XML generation, add it to `docs/GUIDE.md` following the existing format:

```
### C-NNN: Title
- **Issue**: What went wrong
- **Rule**: What to do instead
- **Scope**: Where this applies
```

## Important Rules

- **Never use ElementTree/lxml for TWB editing** — it destroys XML namespaces. Text replacement only. (See C-002)
- **Always validate with XSD** before submitting patterns
- **Include only public/sample data** in examples — no customer or proprietary data

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
