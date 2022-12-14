# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- Added a new way of using the tag helper `vivi.elements.h` to create html
  elements, namely `h['example-tag']`. This is mainly useful for creating tags
  that are not valid python identifiers.
- Added a new parameter `eager` to `vivi.hooks.use_future`, this parameter
  makes the initial response wait on the rerender from this future when true.
- Added a special handling of the prop `ref` on
  `vivi.elements.HTMLElement`-instances. This callable will be called with the
  `vivi.nodes.Node`-instance when mounted and with `None` when unmounted.
- Added a hook `use_file` that when provided a path-like object returns a temp
  url pointing to the file that can only be used by the current user. (Based on
  a cookie.)
- Added a new function `vivi.shared.create_shared`, which you can supply an
  async context manager that returns a resource you want to share among all
  connections. This function then returns a 2-tuple of 2 values:
  - An instance of `vivi.shared.Shared` that you can pass along to the
    `Vivi`-app with the new keyword argument `shared` which accepts an iterable
    of `Shared`-instances and uses their context manager to make sure the
    resource is available when the app is running.
  - A hook that you can use to get the shared resource from within a component.
- Added a new hook `vivi.hooks.use_path` that you can use to resolve a path
  local to the base url where the app is running.
- Added a new hook `vivi.hooks.use_static` that you can use to resolve an url
  to a static file.
- Added three new hooks `vivi.hooks.use_publish`, `vivi.hooks.use_subscribe`
  and `vivi.hooks.use_messages` that together implement a pubsub system.
  `use_publish` returns a function that given a channel and a message
  publishes that message to all subscribers. `use_subscribe` is a decorator
  that given a channel runs the decorated function for every published message
  on that channel. `use_messages` given a channel returns an async iterator
  over messages on that channel. Channels can be any hashable key.

### Changed
- If you call an element positional arguments that are a dict are now
  interpreted as extra props instead of a child. This is mainly useful for
  adding props that are not valid python identifiers.
- Added a target prop to events with the new `vivi.node.Node`-class as value.
- `input` and `submit` events with file inputs as target now have an attribute
  `file` or `files` (based on if they have the `multiple` prop) instead of the
  `value` attribute. These files then again have 2-attributes, `content_type`
  and `content`.
- The hooks returned by `vivi.shared.create_shared` can now also be used from
  within the context managers for shared resources that come later in the
  shared stack. This includes `vivi.hooks.use_publish` and
  `vivi.hooks.use_messages`.

### Fixed
- Fixed unmount crash on websocket close.
- Fixed the href of a `vivi.urls.link` to be correct when running your vivi app
  under a prefixed path.
- Fixed unmount crash when a component used the same context twice.

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

