# SP13-005: Fresh Document Composition From Assets

## Problem

Long term, builds should compose a new Banny document from reusable Studio assets rather than cloning a whole template.

## Scope

- Add a composer that starts from an empty schema v3 document.
- Compose selected scene preset, character tracks, reactions, shots, media, and voice manifest.
- Emit `.bannyshow` as the primary output and pack `.bs` for sharing.

## Acceptance Criteria

- [x] A full episode package can be built from asset registry inputs without a source template package.
- [ ] Banny validation and preview pass on the generated package.
