/**
 * accordion-scroll.js
 * When an exclusive-accordion <details name="..."> opens and causes a
 * prior open sibling to collapse, the browser can scroll off the newly
 * opened card. This script scrolls the summary back into view smoothly.
 *
 * Pure, no-dependency, self-hosted (CSP 'self' safe).
 */
(function () {
    'use strict';
    function onToggle(e) {
        var d = e.target;
        if (!d || d.tagName !== 'DETAILS') return;
        if (!d.open) return;
        // Let the browser finish layout, then scroll the summary into view.
        requestAnimationFrame(function () {
            var s = d.querySelector('summary');
            if (!s) return;
            var rect = s.getBoundingClientRect();
            // Only scroll if the summary is off-screen (above the nav or below the fold).
            if (rect.top < 80 || rect.top > window.innerHeight - 60) {
                s.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    }
    document.addEventListener('toggle', onToggle, true);
})();
