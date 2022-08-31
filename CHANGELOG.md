# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- Added a new way of using the tag helper `vivi.elements.h` to create html
  elements, namely `h['example-tag']`. This is mainly useful for creating tags
  that are not valid python identifiers.

### Changed
- If you call an element positional arguments that are a dict are now
  interpreted as extra props instead of a child. This is mainly useful for
  adding props that are not valid python identifiers.

### Fixed
- Fix unmount crash on websocket close.

## [0.1.1] - 2022-08-31
### Fixed
- Previously the javascript frontend could get confused if a plugin changed the
  DOM. It now keeps its own virtual DOM to guarantee consistency.

## [0.1.0] - 2022-08-30
### Added
- Initial version of the framework.

[Unreleased]: https://github.com/daanvdk/vivi/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/daanvdk/vivi/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/daanvdk/vivi/releases/tag/v0.1.0

