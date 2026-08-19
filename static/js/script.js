document.addEventListener('DOMContentLoaded', function () {
    var tabs = document.querySelectorAll('.toggle-btn');
    var panels = document.querySelectorAll('.forecast-panel');

    tabs.forEach(function (tab) {
        tab.addEventListener('click', function () {
            tabs.forEach(function (button) {
                button.classList.remove('active');
            });
            tab.classList.add('active');

            panels.forEach(function (panel) {
                panel.classList.toggle('hidden', panel.id !== tab.dataset.tab + '-panel');
            });
        });
    });
});