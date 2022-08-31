function createTree(node) {
    return { node, children: Array.from(node.childNodes).map(createTree) };
}
let domTree = null;
window.addEventListener('load', () => domTree = createTree(document));

function getTree(path) {
    let tree = domTree;
    for (const index of path) {
        tree = tree.children[index];
    }
    return tree;
}

function getNode(path) {
    return getTree(path).node;
}

function getPath(node) {
    const nodes = [];
    while (node.parentNode !== null) {
        nodes.push(node);
        node = node.parentNode;
    }

    if (node !== document) {
        throw new Error('node not in dom');
    }

    let tree = domTree;
    const path = [];
    while (nodes.length > 0) {
        const node = nodes.pop();
        const index = tree.children.findIndex((tree) => tree.node === node);
        tree = tree.children[index];
        path.push(index);
    }

    return path;
}

function createNode(data) {
    if (typeof data === 'string') {
        return document.createTextNode(data);
    }
    const [tag, props, ...children] = data;
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props)) {
        node.setAttribute(key, value);
    }
    for (const child of children) {
        node.appendChild(createNode(child));
    }
    return node;
}

const socket = new WebSocket({{socket_url}});

function call(event, preventDefault, stopPropagation, stopImmediatePropagation) {
    if (preventDefault) {
        event.preventDefault();
    }
    if (stopPropagation) {
        event.stopPropagation();
    }
    if (stopImmediatePropagation) {
        event.stopImmediatePropagation();
    }

    const details = {};
    switch (event.type) {
        case 'input': {
            details.value = event.target.value;
        }; break;
        case 'change': {
            details.value = event.target.value;
        }; break;
    }
    socket.send(JSON.stringify([event.type, ...getPath(event.currentTarget), details]));
}

addEventListener('popstate', (event) => {
    socket.send(JSON.stringify(['pop_url', event.state.url]));
});

socket.addEventListener('message', function (event) {
    for (const [action, ...path] of JSON.parse(event.data)) {
        switch (action) {
            case 'insert': {
                const node = createNode(path.pop());
                const index = path.pop();
                const parent = getTree(path);
                if (index === parent.children.length) {
                    parent.node.appendChild(node);
                    parent.children.push(createTree(node));
                } else {
                    parent.node.insertBefore(node, parent.children[index].node);
                    parent.children.splice(index, 0, createTree(node));
                }
            }; break;
            case 'remove': {
                const index = path.pop();
                const parent = getTree(path);
                parent.node.removeChild(parent.children[index].node);
                parent.children.splice(index, 1);
            }; break;
            case 'replace': {
                const node = createNode(path.pop());
                const index = path.pop();
                const parent = getTree(path);
                parent.node.replaceChild(node, parent.children[index].node);
                parent.children[index] = createTree(node);
            }; break;
            case 'move': {
                let newIndex = path.pop();
                const oldIndex = path.pop();
                const parent = getTree(path);
                if (oldIndex === newIndex) {
                    break;
                }
                const [tree] = parent.children.splice(oldIndex, 1);
                if (newIndex === parent.children.length) {
                    parent.node.appendChild(tree.node);
                } else {
                    parent.node.insertBefore(tree.node, parent.children[newIndex].node);
                }
                parent.children.splice(newIndex, 0, tree);
            }; break;
            case 'set': {
                const value = path.pop();
                const key = path.pop();
                const node = getNode(path);
                node.setAttribute(key, value);
            }; break;
            case 'unset': {
                const key = path.pop();
                const node = getNode(path);
                node.removeAttribute(key);
            }; break;
            case 'push_url': {
                const [url] = path;
                history.pushState({ url }, '', url);
            }; break;
            case 'replace_url': {
                const [url] = path;
                history.replaceState({ url }, '', url);
            }; break;
            case 'set_cookie': {
                const [key, value] = path;
                document.cookie = `${encodeURIComponent(key)}=${encodeURIComponent(value)}; path=/`;
            }; break;
            case 'unset_cookie': {
                const [key] = path;
                document.cookie = `${encodeURIComponent(key)}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
            }; break;
        }
    }
});
