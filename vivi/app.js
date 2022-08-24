function getNode(path) {
    let node = document;
    for (const index of path) {
        node = node.childNodes[index];
    }
    return node;
}

function getPath(node) {
    if (node.parentNode === null) {
        return [];
    }
    const path = getPath(node.parentNode);
    for (let i = 0; i < node.parentNode.childNodes.length; i++) {
        if (node === node.parentNode.childNodes[i]) {
            path.push(i);
            return path;
        }
    }
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

function call(event) {
    event.preventDefault();
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
                const parent = getNode(path);
                if (index === parent.childNodes.length) {
                    parent.appendChild(node);
                } else {
                    parent.insertBefore(node, parent.childNodes[index]);
                }
            }; break;
            case 'remove': {
                const index = path.pop();
                const parent = getNode(path);
                parent.removeChild(parent.childNodes[index]);
            }; break;
            case 'replace': {
                const node = createNode(path.pop());
                const index = path.pop();
                const parent = getNode(path);
                parent.replaceChild(node, parent.childNodes[index]);
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
        }
    }
});