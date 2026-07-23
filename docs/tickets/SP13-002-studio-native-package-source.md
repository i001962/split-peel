# SP13-002: Studio-Native Package Source

## Problem

Banny Studio 1.3 treats `.bannyshow` folders and `.bs` packages as valid project sources. split-peel should use unpacked `.bannyshow` folders as the preferred authoring source.

## Scope

- Make package inspection, copying, and build input read `.bannyshow` folders directly.
- Prefer writing editable `.bannyshow` output before packing `.bs`.
- Keep zipped `.bs` as the delivery artifact, not the authoring primitive.

## Acceptance Criteria

- [x] `inspect-template` works on `.bannyshow` folders.
- [x] `build-show` can read a `.bannyshow` source.
- [x] Tests cover folder input.
