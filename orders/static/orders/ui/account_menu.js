(function () {
  'use strict';

  function initialize() {
    const menu = document.getElementById('account-menu');
    if (!menu) return;
    let opener = null;

    // The order screen owns pending writes and draft confirmation. Resolve the
    // hook at departure time so this fragment also works on other screens.
    function canLeave() {
      if (typeof window.BazaarOrder?.canLeave !== 'function') return true;
      try {
        return window.BazaarOrder.canLeave() === true;
      } catch (error) {
        // A broken guard must not allow a navigation or logout to lose a draft.
        return false;
      }
    }

    document.querySelectorAll('[data-account-menu-open]').forEach(button => {
      button.setAttribute('aria-controls', 'account-menu');
      button.setAttribute('aria-haspopup', 'dialog');
      button.setAttribute('aria-expanded', 'false');
    });

    document.addEventListener('click', event => {
      if (!(event.target instanceof Element)) return;
      const button = event.target.closest('[data-account-menu-open]');
      if (!button || event.defaultPrevented) return;
      event.preventDefault();
      if (menu.open) return;
      opener = button;
      menu.showModal();
      opener.setAttribute('aria-expanded', 'true');
    });

    menu.addEventListener('click', event => {
      if (!(event.target instanceof Element)) return;
      if (event.target.closest('[data-account-menu-close]')) {
        event.preventDefault();
        menu.close();
      }
    });

    function guardNavigation(event) {
      if (!(event.target instanceof Element) || event.defaultPrevented) return;
      if (event.type === 'auxclick' && event.button !== 1) return;
      if (event.target.closest('a[href]') && !canLeave()) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    }

    menu.addEventListener('click', guardNavigation, true);
    menu.addEventListener('auxclick', guardNavigation, true);
    menu.addEventListener('submit', event => {
      if (!event.defaultPrevented && !canLeave()) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
      // Keep the native CSRF-protected POST and its existing auth redirect.
    }, true);

    // Native showModal supplies the focus trap and Escape/cancel behavior.
    // Restore to the specific opener for both Escape and the close button.
    menu.addEventListener('close', () => {
      if (opener) {
        opener.setAttribute('aria-expanded', 'false');
        if (opener.isConnected) opener.focus();
      }
      opener = null;
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize, {once: true});
  } else {
    initialize();
  }
})();
