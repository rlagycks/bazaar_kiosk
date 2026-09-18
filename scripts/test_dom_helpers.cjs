/* 4B1: the shared DOM helper never hands a string to the HTML parser.
 *
 * The helper is loaded into a minimal fake document that records every write.
 * A real browser is still the acceptance evidence (see
 * docs/modernization/CONTENT_SECURITY.md); this pins the property in CI: a
 * menu name arrives as text, and an attribute value is set through the DOM.
 */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const HELPER = path.join(__dirname, '..', 'orders', 'static', 'orders', 'ui', 'dom.js');

function createNode(tag) {
  return {
    nodeType: 1,
    tagName: String(tag).toUpperCase(),
    className: '',
    attributes: {},
    listeners: {},
    childNodes: [],
    get firstChild() {
      return this.childNodes[0] || null;
    },
    get textContent() {
      if (this._text !== undefined) return this._text;
      return this.childNodes.map((child) => child.textContent).join('');
    },
    set textContent(value) {
      this._text = String(value);
      this.childNodes = [];
    },
    setAttribute(name, value) {
      this.attributes[name] = String(value);
    },
    getAttribute(name) {
      return Object.prototype.hasOwnProperty.call(this.attributes, name)
        ? this.attributes[name]
        : null;
    },
    addEventListener(event, handler) {
      (this.listeners[event] = this.listeners[event] || []).push(handler);
    },
    appendChild(child) {
      this.childNodes.push(child);
      child.parentNode = this;
      return child;
    },
    removeChild(child) {
      this.childNodes = this.childNodes.filter((one) => one !== child);
      return child;
    },
    contains(other) {
      if (other === this) return true;
      return this.childNodes.some((child) => child.contains && child.contains(other));
    },
    closest(selector) {
      const wanted = selector.replace(/^\[|\]$/g, '');
      let node = this;
      while (node) {
        if (Object.prototype.hasOwnProperty.call(node.attributes || {}, wanted)) return node;
        node = node.parentNode;
      }
      return null;
    },
  };
}

function load() {
  const context = {
    window: {},
    document: {
      createElement: createNode,
      createTextNode(value) {
        return {nodeType: 3, textContent: String(value), childNodes: []};
      },
    },
    Object,
    Array,
    String,
  };
  context.window.document = context.document;
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(HELPER, 'utf8'), context);
  return context.window.BazaarDom;
}

const DOM = load();
const PAYLOAD = '<img src=x onerror="alert(1)">';

test('a payload becomes text, not a child element', () => {
  const node = DOM.el('div', {text: PAYLOAD});
  assert.strictEqual(node.textContent, PAYLOAD);
  assert.strictEqual(node.childNodes.length, 0, 'no element was parsed out of the name');
});

test('a payload passed as a child becomes a text node', () => {
  const node = DOM.el('div', {}, PAYLOAD);
  assert.strictEqual(node.childNodes.length, 1);
  assert.strictEqual(node.childNodes[0].nodeType, 3, 'text node, not an element');
  assert.strictEqual(node.childNodes[0].textContent, PAYLOAD);
});

test('a quote in a data attribute cannot end the attribute', () => {
  const name = 'a" onmouseover="alert(1)';
  const node = DOM.el('button', {data: {name: name}});
  assert.strictEqual(node.getAttribute('data-name'), name);
  assert.strictEqual(node.attributes.onmouseover, undefined);
});

test('a name with a backslash or newline survives unchanged', () => {
  const name = "it's\\ a \n name";
  assert.strictEqual(DOM.el('div', {text: name}).textContent, name);
});

test('render replaces previous children', () => {
  const parent = DOM.el('div', {}, ['old']);
  DOM.render(parent, [DOM.el('span', {text: 'new'})]);
  assert.strictEqual(parent.childNodes.length, 1);
  assert.strictEqual(parent.textContent, 'new');
});

test('clear empties a node', () => {
  const parent = DOM.el('div', {}, ['a', 'b']);
  DOM.clear(parent);
  assert.strictEqual(parent.childNodes.length, 0);
});

test('nullish children are skipped rather than printed', () => {
  const node = DOM.el('div', {}, [null, undefined, false, 'kept']);
  assert.strictEqual(node.textContent, 'kept');
});

test('delegate dispatches to the matching descendant only', () => {
  const container = DOM.el('div');
  const button = DOM.el('button', {data: {action: 'add', id: '7'}});
  container.appendChild(button);
  const seen = [];
  DOM.delegate(container, 'click', '[data-action]', (event, match) => {
    seen.push(match.getAttribute('data-id'));
  });
  container.listeners.click[0]({target: button});
  container.listeners.click[0]({target: DOM.el('div')});
  assert.deepStrictEqual(seen, ['7']);
});

test('an event handler is bound through addEventListener, never an attribute', () => {
  let called = 0;
  const node = DOM.el('button', {on: {click: () => { called += 1; }}});
  assert.strictEqual(node.attributes.onclick, undefined);
  node.listeners.click[0]();
  assert.strictEqual(called, 1);
});
