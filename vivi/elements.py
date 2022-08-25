from abc import ABC, abstractmethod

from .hooks import _ctx


INCOMPATIBLE = 0
COMPATIBLE = 1
EQUIVALENT = 2


class Element(ABC):

    def __init__(self, props, children):
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

    def _rerender(self, path, state, result):
        try:
            head, *tail = path
        except ValueError:
            return self._render(state, result)

        child, child_state, child_result = self._extract(state, result, head)
        child_state, child_result = child._rerender(tail, child_state, child_result)
        return self._insert(state, result, head, child_state, child_result)

    def __call__(self, *args, **kwargs):
        if 'children' in kwargs:
            raise ValueError('\'children\' is not allowed as a property name')

        return self._copy({**self._props, **kwargs}, (*self._children, *args))


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
        elif isinstance(elem, HTMLElement):
            return COMPATIBLE
        else:
            return INCOMPATIBLE

    def _init(self):
        return (), (self._tag, self._props)

    def _render(self, prev_state, prev_result):
        state = []
        child_results = []

        for i, child in enumerate(self._children):
            if i < len(prev_state):
                prev_child, prev_child_state = prev_state[i]
                prev_child_result = prev_result[i + 2]
            else:
                prev_child = None
                prev_child_state = None
                prev_child_result = None

            if isinstance(child, Element):
                comp = child._comp(prev_child)
            else:
                comp = INCOMPATIBLE

            if comp == INCOMPATIBLE:
                if isinstance(prev_child, Element):
                    prev_child._unmount(prev_child_state, prev_child_result)
                if isinstance(child, Element):
                    prev_child_state, prev_child_result = child._init()
                else:
                    prev_child_state = None
                    prev_child_result = child
                _ctx.rerender_paths.prune((*_ctx.path, 'render'))

            if comp == EQUIVALENT:
                path = (*_ctx.path, i)
                if path in _ctx.rerender_paths:
                    comp = COMPATIBLE

            if comp == EQUIVALENT:
                child = prev_child
                child_state = prev_child_state
                child_result = prev_child_result
                for subpath in _ctx.rerender_paths.children(path, stop_at_value=True):
                    old_path = _ctx.path
                    _ctx.path = list(subpath)
                    try:
                        child_state, child_result = child._rerender(subpath[len(path):], child_state, child_result)
                    finally:
                        _ctx.path = old_path

            elif isinstance(child, Element):
                _ctx.path.append(i)
                try:
                    child_state, child_result = child._render(
                        prev_child_state,
                        prev_child_result,
                    )
                finally:
                    _ctx.path.pop()
            else:
                child_state = None
                child_result = child

            state.append((child, child_state))
            child_results.append(child_result)

        for (prev_child, prev_child_state), prev_child_result in zip(
            prev_state[len(self._children):],
            prev_result[len(self._children) + 2:],
        ):
            prev_child._unmount(prev_child_state, prev_child_result)

        return tuple(state), (self._tag, self._props, *child_results)

    def _unmount(self, state, result):
        for (child, child_state), child_result in zip(state, result[2:]):
            if isinstance(child, Element):
                child._unmount(child_state, child_result)

    def _extract(self, state, result, key):
        child, child_state = state[key]
        child_result = result[key + 2]
        return child, child_state, child_result

    def _insert(self, state, result, key, child_state, child_result):
        child, _ = state[key]
        state = (*state[:key], (child, child_state), *state[key + 1:])
        result = (*result[:key + 2], child_result, *result[key + 3:])
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
        return (None, None, None), None

    def _render(self, prev_state, prev_result):
        refs, prev_elem, prev_elem_state = prev_state

        _ctx.refs = [] if refs is None else iter(refs)
        try:
            props = self._props
            if self._children:
                props = {**props, 'children': self._children}
            elem = self._func(**props)

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

        if isinstance(elem, Element):
            comp = elem._comp(prev_elem)
        else:
            comp = INCOMPATIBLE

        if comp == EQUIVALENT:
            path = (*_ctx.path, 'render')
            if path in _ctx.rerender_paths:
                comp = COMPATIBLE

        if comp == EQUIVALENT:
            elem_state = prev_elem_state
            result = prev_result
            for subpath in _ctx.rerender_paths.children(path, stop_at_value=True):
                old_path = _ctx.path
                _ctx.path = list(subpath)
                try:
                    elem_state, result = elem._rerender(subpath[len(path):], elem_state, result)
                finally:
                    _ctx.path = old_path
        else:
            if comp == INCOMPATIBLE:
                if isinstance(prev_elem, Element):
                    prev_elem._unmount(prev_elem_state, prev_result)
                if isinstance(elem, Element):
                    prev_elem_state, prev_result = elem._init()
                else:
                    prev_elem_state = None
                    prev_result = elem
                _ctx.rerender_paths.prune((*_ctx.path, 'render'))

            if isinstance(elem, Element):
                _ctx.path.append('render')
                try:
                    elem_state, result = elem._render(
                        prev_elem_state,
                        prev_result,
                    )
                finally:
                    _ctx.path.pop()
            else:
                elem_state = None
                result = elem

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
