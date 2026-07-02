# Shared Protocol Assets

This directory contains protocol assets that Python code can import or load.

- `docs/protocol/protocol.md` is the human-readable protocol document for design review.
- `shared/protocol/` contains constants and schema files for Python code.
- `robot/firmware/src/protocol.h` should stay synchronized with these constants when firmware message types change.

Keep this directory small and boring. It should define names and examples, not own business logic.

