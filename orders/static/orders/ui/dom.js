/* Building screen content without ever handing a string to the HTML parser.
 *
 * A menu name, table name or order note is operator input. Interpolated into
 * markup it becomes markup: `<img src=x onerror=...>` runs. Interpolated into
 * an inline handler it becomes code, and one `\'` replacement does not survive
 * a name containing a backslash or a newline. Text assigned as text cannot do
 * either, whatever it contains.
 *
 * So: nodes are created, attributes are set through the DOM, and text goes in
 * as text. Events are bound with addEventListener, never through an attribute.
 */
(function () {
  'use strict';

  /** Remove every child of a node. The safe equivalent of emptying markup. */
  function clear(node) {
    if (!node) return node;
    while (node.firstChild) node.removeChild(node.firstChild);
    return node;
  }

  function append(node, child) {
    if (child === null || child === undefined || child === false) return;
    if (Array.isArray(child)) {
      child.forEach(function (one) { append(node, one); });
      return;
    }
    // A string becomes a text node, never parsed markup. This is the point.
    node.appendChild(
      child && child.nodeType ? child : document.createTextNode(String(child))
    );
  }

  /**
   * Create an element.
   *
   * `options.class` sets the class, `options.text` the text content,
   * `options.data` data-* attributes, `options.attrs` plain attributes and
   * `options.on` listeners. Children are text or nodes.
   */
  function el(tag, options, children) {
    const settings = options || {};
    const node = document.createElement(tag);
    if (settings.class) node.className = settings.class;
    if (settings.text !== undefined && settings.text !== null) {
      node.textContent = String(settings.text);
    }
    Object.keys(settings.data || {}).forEach(function (key) {
      // The value lands in the attribute through the DOM, so a quote in a name
      // cannot end the attribute the way string-built markup would let it.
      node.setAttribute('data-' + key, String(settings.data[key]));
    });
    Object.keys(settings.attrs || {}).forEach(function (key) {
      const value = settings.attrs[key];
      if (value === false || value === null || value === undefined) return;
      node.setAttribute(key, value === true ? '' : String(value));
    });
    Object.keys(settings.on || {}).forEach(function (event) {
      node.addEventListener(event, settings.on[event]);
    });
    append(node, children === undefined ? [] : children);
    return node;
  }

  /** Replace a node's children with the given nodes or text. */
  function render(node, children) {
    if (!node) return node;
    clear(node);
    append(node, children);
    return node;
  }

  /**
   * Bind one listener on a container and dispatch by the closest match. Rows
   * can then be rebuilt freely without losing their handlers, and no per-row
   * closure is needed -- which is what the inline handlers were for.
   */
  function delegate(container, event, selector, handler) {
    if (!container) return;
    container.addEventListener(event, function (domEvent) {
      const match = domEvent.target.closest(selector);
      if (match && container.contains(match)) handler(domEvent, match);
    });
  }

  window.BazaarDom = Object.freeze({clear: clear, el: el, render: render, delegate: delegate});
})();
