/* Movie Ad Generator — global state */

var movieState = {
    currentStep: 1,
    project: null,
    kols: [],
    selectedKols: [],
    productData: null,
    imageFiles: [],
    selectedImageIndexes: new Set(),
    fetchedImageUrls: [],
    selectedFetchedIndexes: new Set(),
};
