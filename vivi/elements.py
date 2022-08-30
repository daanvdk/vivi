from abc import ABC, abstractmethod

from .hooks import _ctx
from .node import SafeText


INCOMPATIBLE = object()
COMPATIBLE = object()
EQUIVALENT = object()

INDEX_KEY = object()


class Element(ABC):

    def __init__(self, props, children):
        try:
            self._key = props.pop('key')
        except KeyError:
            pass

        self._props = props
        self._children = children

    @abstractmethod
    def _copy(self, props, children):
        raise NotImplementedError

    @abstractmethod
    def _comp(self, elem):
        raise NotImplementedError

    @abstractmethod
    def _init(self):
        raise NotImplementedError

    @abstractmethod
    def _render(self, prev_state, prev_result):
        raise NotImplementedError

    @abstractmethod
    def _unmount(self, state, result):
        raise NotImplementedError

    @abstractmethod
    def _extract(self, state, result, key):
        raise NotImplementedError

    @abstractmethod
    def _insert(self, state, result, key, child_state, child_result):
        raise NotImplementedError

    def _clean_elem(self, elem):
        if elem is None or isinstance(elem, (SafeText, str)):
            elem = Literal(elem)

        if not isinstance(elem, Element) and not isinstance(elem, str):
            try:
                children = tuple(elem)
            except TypeError:
                pass
            else:
                elem = HTMLElement(None, {}, children)

        if not isinstance(elem, Element):
            elem = Literal(str(elem))

        return elem

    def _rerender(self, prev_elem, prev_state, prev_result):
        comp = self._comp(prev_elem)

        if comp is INCOMPATIBLE:
            prev_elem._unmount(prev_state, prev_result)
            _ctx.rerender_paths.prune(_ctx.path)
            prev_state, prev_result = self._init()

        if comp is EQUIVALENT and _ctx.path not in _ctx.rerender_paths:
            state = prev_state
            result = prev_result

            for subpath in _ctx.rerender_paths.children(
                _ctx.path, stop_at_value=True,
            ):
                path = _ctx.path
                _ctx.path = list(subpath)
                try:
                    state, result = self._rerender_path(
                        subpath[len(path):], state, result,
                    )
                finally:
                    _ctx.path = path
        else:
            state, result = self._render(prev_state, prev_result)

        return state, result

    def _rerender_path(self, path, state, result):
        stack = []
        elem = self

        for key in path:
            stack.append((elem, state, result, key))
            elem, state, result = elem._extract(state, result, key)

        state, result = elem._render(state, result)

        while stack:
            elem, prev_state, prev_result, key = stack.pop()
            state, result = elem._insert(
                prev_state, prev_result, key, state, result,
            )

        assert elem is self
        return state, result

    def __call__(self, *args, **kwargs):
        if 'children' in kwargs:
            raise ValueError('\'children\' is not allowed as a property name')

        return self._copy({**self._props, **kwargs}, (*self._children, *args))


class Literal(Element):

    def __init__(self, value):
        self._value = value

    def _copy(self, props, children):
        raise ValueError('literals cannot be copied')

    def _comp(self, elem):
        if not isinstance(elem, Literal):
            return INCOMPATIBLE
        elif elem._value != self._value:
            return COMPATIBLE
        else:
            return EQUIVALENT

    def _init(self):
        return None, self._value

    def _render(self, prev_state, prev_result):
        return None, self._value

    def _unmount(self, state, result):
        pass

    def _extract(self, state, result, key):
        raise ValueError('literals do not have children')

    def _insert(self, state, result, key, child_state, child_result):
        raise ValueError('literals do not have children')


class HTMLElement(Element):

    def __init__(self, tag, props, children):
        if tag is None and props:
            raise ValueError('fragment cannot have props')

        super().__init__(props, children)
        self._tag = tag

    def _copy(self, props, children):
        return HTMLElement(self._tag, props, children)

    def __eq__(self, other):
        return (
            isinstance(other, HTMLElement) and
            other._tag == self._tag and
            other._props == self._props and
            other._children == self._children
        )

    def _comp(self, elem):
        if elem == self:
            return EQUIVALENT
        elif isinstance(elem, HTMLElement) and elem._tag == self._tag:
            return COMPATIBLE
        else:
            return INCOMPATIBLE

    def _init(self):
        return {}, (self._tag, self._props, {})

    def _render(self, prev_state, prev_result):
        state = {}
        child_results = []
        child_prev_indexes = {}

        prev_state = prev_state.copy()

        for index, child in enumerate(map(self._clean_elem, self._children)):
            try:
                key = child._key
            except AttributeError:
                key = (INDEX_KEY, index)

            if key in state:
                raise ValueError('duplicate keys')

            try:
                prev_child, prev_child_state, prev_index = prev_state.pop(key)
            except KeyError:
                prev_child = Literal(None)
                prev_child_state = None
                prev_child_result = None
            else:
                prev_child_result = prev_result[prev_index + 3]
                child_prev_indexes[index] = prev_index

            _ctx.path.append(key)
            try:
                child_state, child_result = child._rerender(
                    prev_child, prev_child_state, prev_child_result,
                )
            finally:
                _ctx.path.pop()

            state[key] = (child, child_state, index)
            child_results.append(child_result)

        for prev_child, prev_child_state, prev_index in prev_state.values():
            prev_child_result = prev_result[prev_index + 3]
            prev_child._unmount(prev_child_state, prev_child_result)

        result = (self._tag, self._props, child_prev_indexes, *child_results)
        return state, result

    def _unmount(self, state, result):
        for child, child_state, index in state.values():
            child_result = result[index + 3]
            child._unmount(child_state, child_result)

    def _extract(self, state, result, key):
        child, child_state, index = state[key]
        child_result = result[index + 3]
        return child, child_state, child_result

    def _insert(self, state, result, key, child_state, child_result):
        child, _, index = state[key]
        state = {**state, key: (child, child_state, index)}

        tag, props, _, *children = result
        result = (
            tag, props,
            {i: i for i in range(len(children))},
            *children[:index], child_result, *children[index + 1:],
        )

        return state, result


class Component(Element):

    def __init__(self, func, props, children):
        super().__init__(props, children)
        self._func = func

    def _copy(self, props, children):
        return Component(self._func, props, children)

    def __eq__(self, other):
        return (
            isinstance(other, Component) and
            other._func == self._func and
            other._props == self._props and
            other._children == self._children
        )

    def _comp(self, elem):
        if elem == self:
            return EQUIVALENT
        elif isinstance(elem, Component) and elem._func == self._func:
            return COMPATIBLE
        else:
            return INCOMPATIBLE

    def _init(self):
        return (None, Literal(None), None), None

    def _render(self, prev_state, prev_result):
        refs, prev_elem, prev_elem_state = prev_state

        _ctx.refs = [] if refs is None else iter(refs)
        try:
            props = self._props
            if self._children:
                props = {**props, 'children': self._children}
            elem = self._clean_elem(self._func(**props))

            if refs is None:
                refs = tuple(_ctx.refs)
            else:
                try:
                    next(_ctx.refs)
                except StopIteration:
                    pass
                else:
                    raise ValueError('less refs used than previous render')
        finally:
            del _ctx.refs

        _ctx.path.append('render')
        try:
            elem_state, result = elem._rerender(
                prev_elem, prev_elem_state, prev_result,
            )
        finally:
            _ctx.path.pop()

        return (refs, elem, elem_state), result

    def _unmount(self, state, result):
        refs, elem, elem_state = state
        if isinstance(elem, Element):
            elem._unmount(elem_state, result)
        for ref in refs:
            if hasattr(ref, '_vivi_cleanup'):
                ref._vivi_cleanup()

    def _extract(self, state, result, key):
        assert key == 'render'
        _, child, child_state = state
        return child, child_state, result

    def _insert(self, state, result, key, child_state, child_result):
        assert key == 'render'
        refs, child, _ = state
        return (refs, child, child_state), child_result


class HTMLFactory:

    def __getattr__(self, name):
        return HTMLElement(name, {}, ())


h = HTMLFactory()


def component(func):
    return Component(func, {}, ())


fragment = HTMLElement(None, {}, ())
