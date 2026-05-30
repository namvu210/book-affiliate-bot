/* App initialization: runs on DOMContentLoaded */

document.addEventListener('DOMContentLoaded', function () {
    loadPlatforms();
    loadModels();
    loadKolStatus();
    loadGlobalVoices();
    onGlobalVoiceChange();
    loadReviewStyles();
    initForms();
    startShopeePolling();
    applyPreset('product');
});
