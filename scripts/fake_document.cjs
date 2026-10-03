// Minimal event/focus DOM for controller unit tests; native layout is checked in-browser.
function fakeDocument() {
  let document;
  class Node {
    constructor(tag, attrs = {}) {
      this.tag = tag; this.attrs = {}; this.dataset = {}; this.children = [];
      this.listeners = new Map(); this.parent = null; this.value = '';
      this.disabled = false; this.hidden = false; this.open = false;
      this._checked = false; this._text = '';
      Object.entries(attrs).forEach(([key, value]) => this.setAttribute(key, value));
    }
    setAttribute(key, value) {
      key = key.toLowerCase();
      this.attrs[key] = String(value);
      if (key === "value") this.value = String(value);
      if (key.startsWith('data-')) {
        this.dataset[key.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = String(value);
      }
    }
    get isConnected() { return this === document || Boolean(this.parent?.isConnected); }
    get checked() { return this._checked; }
    set checked(value) {
      if (value && this.attrs.name) {
        document.querySelectorAll(`input[name="${this.attrs.name}"]`).forEach(node => { node._checked = false; });
      }
      this._checked = value;
    }
    get textContent() { return this._text + this.children.map(node => node.textContent).join(''); }
    set textContent(value) { this._text = String(value); this.replaceChildren(); }
    replaceChildren(...nodes) {
      this.children.forEach(node => { node.parent = null; });
      this.children = nodes; nodes.forEach(node => { node.parent = this; });
    }
    append(node) { this.children.push(node); node.parent = this; return node; }
    matches(selector) {
      const parts = selector.trim().split(/\s+/);
      const own = parts.pop();
      const tag = own.match(/^[a-z]+/);
      if (tag && this.tag !== tag[0]) return false;
      for (const [, name] of own.matchAll(/\.([\w-]+)/g)) {
        if (!(this.attrs.class || '').split(' ').includes(name)) return false;
      }
      for (const [, key, value] of own.matchAll(/\[([\w-]+)(?:="([^"]*)")?\]/g)) {
        if (!(key in this.attrs) || (value !== undefined && this.attrs[key] !== value)) return false;
      }
      if (own.includes(':checked') && !this.checked) return false;
      if (!parts.length) return true;
      for (let parent = this.parent; parent; parent = parent.parent) {
        if (parent.matches(parts.join(' '))) return true;
      }
      return false;
    }
    querySelectorAll(selector) {
      const nodes = this.children.flatMap(child => [child, ...child.querySelectorAll('*')]);
      return nodes.filter(node => selector.split(',').some(part => node.matches(part)));
    }
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
    closest(selector) { return this.matches(selector) ? this : this.parent?.closest(selector); }
    addEventListener(type, handler) {
      if (!this.listeners.has(type)) this.listeners.set(type, []);
      this.listeners.get(type).push(handler);
    }
    dispatch(type) {
      const event = {type, target: this, defaultPrevented: false,
        preventDefault() { this.defaultPrevented = true; }};
      const pending = [];
      for (let node = this; node; node = node.parent) {
        event.currentTarget = node;
        for (const handler of node.listeners.get(type) || []) pending.push(handler(event));
      }
      return Promise.all(pending);
    }
    focus() {
      if (this.disabled) return;
      for (let node = this; node; node = node.parent) if (node.hidden) return;
      document.activeElement = this;
    }
    setSelectionRange(start, end) { this.selectionStart = start; this.selectionEnd = end; }
    showModal() { this.open = true; }
    close() { this.open = false; }
  }
  document = new Node('document');
  document.cookie = 'csrftoken=synthetic-csrf';
  document.getElementById = id => document.querySelector(`[id="${id}"]`);
  document.create = (tag, attrs) => new Node(tag, attrs);
  return document;
}

module.exports = {fakeDocument};
