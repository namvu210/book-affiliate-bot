/* Movie Ad Generator — page initialization */

document.addEventListener('DOMContentLoaded', function () {
    loadKolList();
    loadStoryStyles();
    loadClipModels();
    loadMusicCategories();
    initMovieImageDropzone();
    updateStepStatus();
});

function updateStepStatus() {
    var steps = document.querySelectorAll('.wizard-step');
    steps.forEach(function (el, i) {
        var num = i + 1;
        if (num < movieState.currentStep) {
            el.classList.add('done');
            el.classList.remove('active');
        } else if (num === movieState.currentStep) {
            el.classList.add('active');
            el.classList.remove('done');
        } else {
            el.classList.remove('active', 'done');
        }
    });

    var panels = document.querySelectorAll('.step-panel');
    panels.forEach(function (el, i) {
        el.style.display = (i + 1 === movieState.currentStep) ? 'block' : 'none';
    });

    var nextBtn = document.getElementById('btn-next-step');
    if (nextBtn) {
        if (movieState.currentStep === 1) {
            nextBtn.disabled = movieState.selectedKols.length === 0;
        }
    }

    // Render scene images when entering step 4
    if (movieState.currentStep === 4) {
        renderSceneImagesStep();
    }

    // Render video clips when entering step 5
    if (movieState.currentStep === 5) {
        renderVideoClipsStep();
    }

    // Render assembly when entering step 6
    if (movieState.currentStep === 6) {
        renderAssemblyStep();
    }
}

function goToStep(step) {
    if (step < 1 || step > 6) return;
    movieState.currentStep = step;
    updateStepStatus();
}

function nextStep() {
    if (movieState.currentStep === 1 && movieState.selectedKols.length === 0) {
        alert('Chọn ít nhất 1 KOL');
        return;
    }
    goToStep(movieState.currentStep + 1);
}

function prevStep() {
    goToStep(movieState.currentStep - 1);
}
