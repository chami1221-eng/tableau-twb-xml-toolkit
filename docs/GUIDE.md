# TWB XML Generation Guide

Rules and patterns for generating Tableau .twb workbook files via XML text manipulation.

## Prerequisites

- Target: Tableau Desktop 2025.2+ compatible `.twb` (version 18.1)
- CSV files as data source
- Post-generation fine-tuning via Desktop or Tableau Agent

## Workflow

1. **Analyze CSVs** - Check headers, data types, row counts, join keys
2. **Design datasources** - Plan JOINs, standalone CSVs, worksheet types
3. **Generate .twb** - Python script outputting XML via f-strings (text manipulation only)
4. **Validate** - `publish_test.py --xsd` for XSD schema check
5. **Publish** - `publish.py` for Tableau Cloud upload
6. **Verify** - `tools/tableau_rest.py view-image` for visual confirmation (no MCP server needed)

## Credentials

Store PAT in `~/.env.tableau` (never paste directly in chat or code):

```
TABLEAU_PAT_NAME=your_pat_name
TABLEAU_PAT_SECRET=your_pat_secret
TABLEAU_SERVER=https://your-server.online.tableau.com
TABLEAU_SITE_ID=your_site_id
```

## .twb XML Rules

### Manifest

```xml
<document-format-change-manifest>
  <ManifestByVersion />
</document-format-change-manifest>
```

`ManifestByVersion` replaces 8 individual flags (AnimationOnByDefault, etc.) in a single element.
Tableau 2026.1 XSD officially supports this. The old 8-flag format still works.

### Datasource Structure

Each datasource requires:
1. `<named-connections>` - CSV connection definition
2. `<relation>` - Table or JOIN relation
3. `<metadata-records>` - Column metadata with `<object-id>`
4. `<column>` definitions - role/type/semantic-role
5. `<object-graph>` - ObjectModelEncapsulateLegacy support

### Mapsources (when using maps)

Required in two places:
1. **Workbook level**: Between `</datasources>` and `<worksheets>`
2. **Map worksheet `<view>`**: After `<datasources>`

```xml
<mapsources>
  <mapsource name='Tableau' />
</mapsources>
```

### Geographic Columns

```xml
<column aggregation='Avg' caption='Latitude' datatype='real' name='[lat]'
        role='measure' semantic-role='[Geographical].[Latitude]' type='quantitative' />
```

- `aggregation='Avg'` (Sum breaks coordinates)
- `semantic-role='[Geographical].[Latitude]'` or `[Longitude]`

### Dashboard

Content model order:
```
style > size > datasources > datasource-dependencies* > zones > devicelayouts > simple-id
```

- Empty `<dashboards />` is invalid. Include at least one `<dashboard>` or omit the element.
- Use `layout-basic` with absolute positioning for reliable rendering.

### JOIN Definition

```xml
<relation join='left' type='join'>
  <clause type='join'>
    <expression op='='>
      <expression op='[table1.csv].[key_col]' />
      <expression op='[table2.csv].[key_col]' />
    </expression>
  </clause>
  <relation connection='nc_id1' name='table1.csv' table='[table1#csv]' type='table'>
    <columns>...</columns>
  </relation>
  <relation connection='nc_id2' name='table2.csv' table='[table2#csv]' type='table'>
    <columns>...</columns>
  </relation>
</relation>
```

Multi-table JOINs are nested: `((A JOIN B) JOIN C) JOIN D`

## Advanced Dashboard Features

See `twb-patterns.md` for complete XML snippets.

| Feature | XML Pattern | Complexity |
|---------|-------------|------------|
| Filter Action | `tsc:tsl-filter` + `exclude-sheet` | Low |
| Highlight | `tsc:brush` | Low |
| Parameter Action | `edit-parameter-action` | Medium |
| Set Action | `edit-group-action` + `<group>` | Medium |
| Dynamic Zone Visibility | `datagraph` + `dashboard-zone-visibility-node` | High |
| Show/Hide Toggle | `<button>` + `<toggle-action>` | Medium |
| Go-to-sheet | `tabdoc:goto-sheet window-id="{GUID}"` | Low |
| Reference Line | `<reference-line>` + `<style-rule element='refline'>` | Low |
| Dual Axis | rows `+` combine + 2nd pane `y-axis-name` | Medium |
| Custom Colors | `<color-palette>` in `<preferences>` | Low |
| Spatial Functions | BUFFER/INTERSECTS/MAKEPOINT/MAKELINE | Medium |

## Correction Records

Rules learned from publish failures and rendering issues. **Check before generating TWBs.**

### C-001: Publish 403 = suspect XML structure, not PAT
- **Incident**: Repeatedly re-issued PATs when the actual cause was XML incompatibility
- **Rule**: Use a working TWB as template. Don't suspect PAT first.

### C-002: Never use ElementTree for editing
- **Incident**: ET round-trip destroyed `user:` namespace and attribute order -> Cloud 403
- **Rule**: TWB XML editing must use **text replacement only**. ElementTree/lxml forbidden for writes.
- **Exception**: Read-only validation (XSD, XPath search) with lxml is OK.

### C-003: Don't force styling
- **Incident**: Embedding fonts/colors in XML produced worse results than Tableau defaults
- **Rule**: Keep `<style />` empty. Let Tableau handle defaults.

### C-004: Dashboard = layout-basic with absolute positioning
- **Incident**: layout-flow caused data-heavy worksheets to compress others
- **Rule**: Use layout-basic with absolute zone positioning.

### C-005: BAN cards use row-level calculations
- **Incident**: SUM() + derivation='Sum' = double aggregation -> blank output
- **Rule**: Use row-level expressions. Don't include aggregate functions in encodings.

### C-006: Filters/legends beside source chart
- **Incident**: All filters grouped at dashboard top -> poor usability
- **Rule**: Place filters next to their target worksheet. Include legends in both dashboards.

### C-007: customized-label/tooltip field reference scope
- **Incident**: Defined field in datasource-dependencies but label didn't display it
- **Rule**: Only fields used in encodings can be referenced in labels/tooltips.

## XSD Schema Validation

Official Tableau XSD (released Feb 2026) validates TWB structure. Stored locally in `schemas/`.

```bash
# XSD validation only (no publish)
python tools/publish_test.py your_file.twb --xsd

# XSD + publish test
python tools/publish_test.py your_file.twb csv_dir/ --xsd --project-id <id>

# Re-download XSD (when updated)
python tools/publish_test.py --download-xsd
```

**Validates**: Element order, required attributes, attribute patterns, manifest structure
**Does not validate**: Connection strings, formulas, field name references, TWBX, semantic correctness

**Known warnings (non-blocking)**: fontstyle attribute, sort/computed-sort order, trendline order, missing trailing elements

## References

- **twb-patterns.md** - XML pattern catalog (57+ patterns from 80+ visualizations)
- [Tableau Document Schemas (GitHub)](https://github.com/tableau/tableau-document-schemas) - Official XSD
