/* 新闻早报 · 交互 */
(function () {
    'use strict';

    var doc = document.documentElement;
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    /* ---------------- 深浅色 ---------------- */
    function applyTheme(mode) {
        doc.setAttribute('data-theme', mode);
        doc.style.colorScheme = mode;
        try { localStorage.setItem('brief-theme', mode); } catch (e) {}
        var meta = document.querySelector('meta[name="theme-color"]');
        if (meta) meta.setAttribute('content', mode === 'dark' ? '#262624' : '#faf9f5');
    }

    var toggle = document.getElementById('theme-toggle');
    if (toggle) {
        toggle.addEventListener('click', function () {
            applyTheme(doc.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
        });
    }
    applyTheme(doc.getAttribute('data-theme') || 'light');

    /* ---------------- 顶栏描边 ---------------- */
    var bar = document.getElementById('topbar');
    var ticking = false;
    function onScroll() {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(function () {
            ticking = false;
            if (!bar) return;
            bar.classList.toggle('is-scrolled', (window.pageYOffset || 0) > 8);
        });
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();

    /* ---------------- 归档搜索 ---------------- */
    var input = document.getElementById('archive-search');
    if (input) {
        var rows = Array.prototype.slice.call(document.querySelectorAll('.day-row'));
        var months = Array.prototype.slice.call(document.querySelectorAll('.month'));
        var count = document.getElementById('search-count');
        var empty = document.getElementById('archive-empty');
        var timer = null;

        var run = function () {
            var q = input.value.trim().toLowerCase();
            var hits = 0;
            rows.forEach(function (row) {
                var key = (row.getAttribute('data-k') || '').toLowerCase();
                var show = !q || key.indexOf(q) !== -1;
                row.hidden = !show;
                if (show) hits++;
            });
            months.forEach(function (m) {
                m.hidden = m.querySelectorAll('.day-row:not([hidden])').length === 0;
            });
            if (count) count.textContent = q ? hits + ' / ' + rows.length : '';
            if (empty) empty.hidden = !(q && hits === 0);
        };

        input.addEventListener('input', function () {
            clearTimeout(timer);
            timer = setTimeout(run, 120);
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === '/' && document.activeElement !== input) {
                e.preventDefault();
                input.focus();
                input.select();
            }
        });
    }

    /* ---------------- 入场 ---------------- */
    var items = Array.prototype.slice.call(document.querySelectorAll('[data-reveal]'));
    if (!items.length) return;
    if (!('IntersectionObserver' in window) || reduce) {
        items.forEach(function (el) { el.classList.add('is-in'); });
    } else {
        var io = new IntersectionObserver(function (entries) {
            entries.forEach(function (en) {
                if (!en.isIntersecting) return;
                en.target.classList.add('is-in');
                io.unobserve(en.target);
            });
        }, { threshold: 0.08, rootMargin: '0px 0px -4% 0px' });
        items.forEach(function (el) { io.observe(el); });
    }
})();
