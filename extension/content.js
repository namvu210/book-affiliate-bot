// Content script — runs on Shopee product pages
// Scrapes product data when requested by the popup

async function scrollToReviews() {
  // Step 1: Scroll down in steps to load lazy content
  const step = window.innerHeight;
  const totalHeight = document.body.scrollHeight;
  for (let pos = 0; pos < totalHeight; pos += step) {
    window.scrollTo(0, pos);
    await new Promise(r => setTimeout(r, 250));
  }

  // Step 2: Find and click the review tab button
  const hasReviews = () => document.querySelectorAll('.shopee-product-comment-list > div, [class*="comment-list"] > div, [class*="shopee-product-rating"] > div').length > 0;

  const buttons = document.querySelectorAll('button');
  for (const btn of buttons) {
    const t = btn.textContent.trim().toLowerCase();
    if (t.match(/đánh giá/) && t.length < 25 && !btn.closest('a')) {
      btn.scrollIntoView({ block: 'center' });
      await new Promise(r => setTimeout(r, 300));
      btn.click();
      await new Promise(r => setTimeout(r, 2500));
      break;
    }
  }

  // Step 3: Wait for reviews to load
  for (let attempt = 0; attempt < 5; attempt++) {
    if (hasReviews()) return;
    window.scrollBy(0, 300);
    await new Promise(r => setTimeout(r, 1000));
  }
}

function scrapeProductData() {
  const url = window.location.href.split('?')[0];

  // Title
  const titleEl = document.querySelector('span.VCeeFx') ||
    document.querySelector('[data-sqe="name"]') ||
    document.querySelector('.product-briefing h1') ||
    document.querySelector('h1');
  const title = titleEl?.textContent?.trim() || '';

  // Price — try known class first, then pattern scan
  let price = '';
  const priceSelectors = ['.IZPeQz', '.pmmxKx', '[aria-label="current price"]',
    '[class*="pdp-price"]', '[class*="item-price"]'];
  for (const sel of priceSelectors) {
    const el = document.querySelector(sel);
    if (el && el.textContent.match(/₫|\d/)) { price = el.textContent.trim(); break; }
  }
  // Fallback: find element matching "₫X" or "X₫" pattern (leaf nodes only)
  if (!price) {
    const els = document.querySelectorAll('div, span');
    for (const el of els) {
      if (el.children.length > 0) continue;
      const t = el.textContent.trim();
      // Match: "₫215.000", "1.300.000₫", "₫215.000 - ₫350.000"
      if (t.match(/^(₫[\d.,]+|[\d.,]+₫)(\s*-\s*(₫[\d.,]+|[\d.,]+₫))?$/) && t.length < 40) {
        price = t;
        break;
      }
    }
  }

  // Description — find the actual product description text
  let description = '';
  // Strategy: find "MÔ TẢ SẢN PHẨM" or "Mô tả" section and grab text after it
  const allSections = document.querySelectorAll('[class*="product-detail"], [class*="pdp-desc"], [class*="item-desc"]');
  for (const section of allSections) {
    const fullText = section.textContent || '';
    // Find where the actual description starts (after headers/breadcrumbs)
    const descMarkers = ['MÔ TẢ SẢN PHẨM', 'Mô tả'];
    for (const marker of descMarkers) {
      const idx = fullText.indexOf(marker);
      if (idx >= 0) {
        let desc = fullText.substring(idx + marker.length).trim();
        // Remove "Mô tả" if it appears again at the start
        desc = desc.replace(/^Mô tả\s*/i, '');
        if (desc.length > 20) {
          description = desc.substring(0, 3000);
          break;
        }
      }
    }
    if (description) break;
  }
  // Fallback: just grab any large text block in product detail
  if (!description) {
    for (const section of allSections) {
      const text = section.textContent?.trim() || '';
      if (text.length > 50) {
        description = text.substring(0, 3000);
        break;
      }
    }
  }

  // Rating
  let rating = null;
  let ratingCount = 0;
  const ratingEl = document.querySelector('.F9RHbS') ||
    document.querySelector('[class*="rating"] [class*="score"]') ||
    document.querySelector('.product-rating-overview__rating-score');
  if (ratingEl) {
    const val = parseFloat(ratingEl.textContent.trim());
    if (val > 0 && val <= 5) rating = val;
  }
  // Fallback: find "X.Y" that looks like a rating score
  if (!rating) {
    const els = document.querySelectorAll('span, div');
    for (const el of els) {
      const t = el.textContent.trim();
      if (t.match(/^[1-4]\.\d$/) && el.closest('[class*="rating"]')) {
        rating = parseFloat(t);
        break;
      }
    }
  }

  // Rating count — use review tab button as primary source (most reliable, product-specific)
  // The tab shows "103\nđánh giá" or "7,3k\nđánh giá"
  const reviewButtons = document.querySelectorAll('button');
  for (const btn of reviewButtons) {
    const t = btn.textContent.trim();
    const m = t.match(/([\d.,]+)\s*([kK])?\s*\n?\s*(đánh giá|Đánh Giá|Ratings)/i);
    if (m && t.length < 30 && !btn.closest('[class*="shop"], [class*="seller"]')) {
      let n = parseFloat(m[1].replace(',', '.'));
      if (m[2]) n *= 1000;
      ratingCount = Math.round(n);
      break;
    }
  }
  // Fallback: look for standalone "NUMBER đánh giá" near rating score, skip shop section
  if (!ratingCount) {
    const els = document.querySelectorAll('span, div, label');
    for (const el of els) {
      if (el.closest('[class*="shop"], [class*="seller"], [class*="store"]')) continue;
      const t = el.textContent.trim();
      let m = t.match(/^([\d.,]+)\s*([kK])?\s*(Đánh Giá|đánh giá|Ratings)$/);
      if (m) {
        let n = parseFloat(m[1].replace(',', '.'));
        if (m[2]) n *= 1000;
        ratingCount = Math.round(n);
        break;
      }
      m = t.match(/^Đánh [Gg]iá\s*([\d.,]+)\s*([kK])?$/);
      if (m) {
        let n = parseFloat(m[1].replace(',', '.'));
        if (m[2]) n *= 1000;
        ratingCount = Math.round(n);
        break;
      }
    }
  }

  // Sold count — "Đã bán 2", "Đã bán 5,2k", "1.234 Đã Bán"
  let soldCount = 0;
  const soldEls = document.querySelectorAll('span, div, a, label');
  for (const el of soldEls) {
    if (el.children.length > 2) continue;
    const t = el.textContent.trim();
    let m = t.match(/^Đã [Bb]án\s*([\d.,]+)\s*([kK])?/);
    if (!m) m = t.match(/^([\d.,]+)\s*([kK])?\s*Đã [Bb]án$/);
    if (m) {
      let n = parseFloat(m[1].replace(',', '.'));
      if (m[2]) n *= 1000;
      soldCount = Math.round(n);
      break;
    }
  }

  // Reviews — scrape and clean
  const reviews = [];
  const reviewEls = document.querySelectorAll('[class*="comment-list"] > div, [class*="shopee-product-rating"] > div, [class*="product-rating__content"], [class*="review-comment"]');
  reviewEls.forEach(el => {
    // Try specific sub-elements first, then fall back to full text
    let text = el.querySelector('[class*="content"], [class*="main-comment"], [class*="comment-text"]')?.textContent?.trim();
    if (!text) text = el.textContent?.trim();
    if (!text || text.length < 10) return;

    // Clean review text
    text = text
      // Username + date: "t*****02025-01-11 12:47 |" or "username2024-05-01 09:30"
      .replace(/^[\w.*]{1,25}\d{4}-\d{2}-\d{2}\s*\d{2}:\d{2}\s*\|?\s*/g, '')
      // "Phân loại hàng: Da,S" — eat colon + up to 30 chars until next sentence
      .replace(/Phân loại hàng:[^.!?]{0,30}(?=[A-ZÀ-Ỹ])/gi, '')
      .replace(/Phân loại hàng:\s*\S{0,25}\s*/gi, '')
      // Remove variant prefix at start: "Đen,XL", "đồng,M", "Trắng,M" etc.
      .replace(/^[A-Za-zÀ-ỹ][\wÀ-ỹ\s-]*,\s*(?:FREESIZE|FREE|5XL|4XL|3XL|XXL|2XL|XL|XXS|XS|S|M|L|\d{2,3})\b\s*/i, '')
      .replace(/\d+:\d+/g, '') // video timestamps
      .replace(/\d*\s*(báo cáo|hữu ích\??)/gi, '') // action buttons
      .replace(/Tố cáo/g, '')
      // Shopee structured review fields
      .replace(/Chất lượng sản phẩm:\s*\S{0,20}\s*/gi, '')
      .replace(/Đúng với mô tả:\s*\S{0,20}\s*/gi, '')
      .replace(/Thời gian giao hàng:\s*\S{0,20}\s*/gi, '')
      .replace(/Dịch vụ của người bán:\s*\S{0,20}\s*/gi, '')
      .replace(/Chất liệu:\s*\S{0,20}\s*/gi, '')
      // Partial leftover from structured fields: "liệu: lụa", "sắc: đen"
      .replace(/^(liệu|sắc|tả|phẩm):\s*\S{0,20}\s*/gi, '')
      .replace(/Màu sắc:\s*\S{0,20}\s*/gi, '')
      .replace(/^(đúng|tốt|nhanh|ổn|chậm)\s*/gi, '') // leftover single-word ratings
      // Remove seller response that gets concatenated
      .replace(/phản hồi của Người Bán.*/gi, '')
      .replace(/Phản Hồi Của Người Bán.*/gi, '')
      .trim();

    if (text.length < 10) return;

    const starsEl = el.querySelectorAll('[class*="icon-rating-solid"], .icon-star-yellow, [class*="full"], svg[class*="star"]');
    const starRating = starsEl.length || 5;
    const likesEl = el.querySelector('[class*="like-count"]');
    const likes = likesEl ? parseInt(likesEl.textContent.replace(/\D/g, '') || '0') : 0;

    reviews.push({ text: text.substring(0, 200), rating: starRating, likes });
  });

  return { url, title, price, description, rating, rating_count: ratingCount, sold_count: soldCount, reviews };
}

function debugSelectors() {
  // Find price candidates: leaf elements containing ₫ + digits
  const priceCandidates = [...document.querySelectorAll('*')].filter(e => {
    const t = e.textContent.trim();
    return t.match(/₫/) && e.children.length === 0 && t.length < 40;
  }).slice(0, 8).map(e => ({ tag: e.tagName, class: e.className.substring(0, 50), text: e.textContent.trim() }));

  // Find rating count candidates
  const ratingCandidates = [...document.querySelectorAll('*')].filter(e => {
    const t = e.textContent.trim();
    return t.match(/Đánh Giá|đánh giá|Ratings/i) && t.length < 40;
  }).slice(0, 8).map(e => ({ tag: e.tagName, class: e.className.substring(0, 50), text: e.textContent.trim() }));

  // Find sold count candidates
  const soldCandidates = [...document.querySelectorAll('*')].filter(e => {
    const t = e.textContent.trim();
    return t.match(/Đã [Bb]án|sold/i) && t.length < 30;
  }).slice(0, 5).map(e => ({ tag: e.tagName, class: e.className.substring(0, 50), text: e.textContent.trim() }));

  // Find review tab candidates (elements with "Đánh Giá" that could be tabs)
  const reviewTabCandidates = [...document.querySelectorAll('div, span, button, label')].filter(e => {
    const t = e.textContent.trim();
    return t.match(/đánh giá/i) && t.length < 30 && !e.closest('a');
  }).slice(0, 10).map(e => ({
    tag: e.tagName, class: e.className?.substring?.(0, 60) || '', text: e.textContent.trim(),
    role: e.getAttribute('role'), children: e.children.length, parent: e.parentElement?.className?.substring?.(0, 40) || ''
  }));

  // Find existing review content using known selectors
  const reviewEls = document.querySelectorAll('[class*="shopee-product-rating"], [class*="product-rating__content"], [class*="review-comment"], [class*="comment-list"] > div');

  // Find potential review containers: elements with text 50-500 chars that look like user reviews
  const reviewTextCandidates = [...document.querySelectorAll('div, p, span')].filter(e => {
    const t = e.textContent.trim();
    return t.length > 40 && t.length < 500 && e.children.length < 3 &&
      !t.match(/₫|Mô tả|hashtag|#\w/) && !e.closest('header, nav');
  }).slice(0, 8).map(e => ({
    tag: e.tagName, class: e.className?.substring?.(0, 50) || '',
    text: e.textContent.trim().substring(0, 80),
    parent: e.parentElement?.className?.substring?.(0, 40) || ''
  }));

  return { priceCandidates, ratingCandidates, soldCandidates, reviewTabCandidates, reviewCount: reviewEls.length, reviewTextCandidates };
}

// Listen for messages from popup
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'scrape') {
    (async () => {
      try {
        // Only scrape product pages (contain "-i." + shopId.itemId pattern)
        if (!window.location.href.match(/-i\.\d+\.\d+/)) {
          sendResponse({ success: false, error: 'Not a product page' });
          return;
        }
        await scrollToReviews();
        const data = scrapeProductData();
        sendResponse({ success: true, data });
      } catch (e) {
        sendResponse({ success: false, error: e.message });
      }
    })();
  } else if (msg.action === 'debug') {
    try {
      const info = debugSelectors();
      sendResponse({ success: true, data: info });
    } catch (e) {
      sendResponse({ success: false, error: e.message });
    }
  } else if (msg.action === 'debug-reviews') {
    (async () => {
      try {
        // Step 1: scroll to bottom
        const step = window.innerHeight;
        for (let pos = 0; pos < document.body.scrollHeight; pos += step) {
          window.scrollTo(0, pos);
          await new Promise(r => setTimeout(r, 200));
        }
        await new Promise(r => setTimeout(r, 500));

        // Step 2: find the review tab button and click it
        let clickedBtn = null;
        const buttons = document.querySelectorAll('button');
        for (const btn of buttons) {
          const t = btn.textContent.trim().toLowerCase();
          if (t.match(/đánh giá/) && t.length < 25) {
            btn.scrollIntoView({ block: 'center' });
            await new Promise(r => setTimeout(r, 300));
            btn.click();
            clickedBtn = { text: btn.textContent.trim(), class: btn.className?.substring(0, 50) };
            break;
          }
        }

        // Step 3: wait longer for content to load
        await new Promise(r => setTimeout(r, 3000));

        // Step 4: scan page for any images from shopee user content (avatar pattern)
        const avatarImgs = [...document.querySelectorAll('img')].filter(img => {
          const src = img.src || '';
          return src.includes('f.shopee') || (src.includes('susercontent') && src.includes('user'));
        }).slice(0, 5).map(img => ({
          src: img.src.substring(0, 80),
          parent: img.parentElement?.className?.substring?.(0, 40) || '',
          grandparent: img.parentElement?.parentElement?.className?.substring?.(0, 40) || ''
        }));

        // Step 5: find content that appeared after the tab area — look for repeated sibling divs with similar structure
        const allDivs = document.querySelectorAll('div');
        const repeatedStructures = [];
        for (const div of allDivs) {
          // Reviews are typically repeated elements — find parent with 3+ similar children
          if (div.children.length >= 3 && div.children.length <= 30) {
            const childClasses = [...div.children].map(c => c.className).filter(Boolean);
            const firstClass = childClasses[0];
            if (firstClass && childClasses.filter(c => c === firstClass).length >= 3) {
              const sampleChild = div.children[0];
              const sampleText = sampleChild.textContent.substring(0, 100);
              if (sampleText.length > 20 && !sampleText.includes('₫') && !sampleText.includes('#')) {
                repeatedStructures.push({
                  parentClass: div.className?.substring(0, 50) || '',
                  childCount: div.children.length,
                  childClass: firstClass.substring(0, 50),
                  sampleText: sampleText
                });
              }
            }
          }
          if (repeatedStructures.length >= 5) break;
        }

        // Step 6: dump the page HTML size and visible text near bottom
        const bottomText = document.body.textContent.substring(
          Math.max(0, document.body.textContent.length - 2000)
        ).substring(0, 500);

        sendResponse({ success: true, data: {
          clickedBtn,
          avatarImgs,
          repeatedStructures,
          bottomText,
          pageHeight: document.body.scrollHeight,
          bodyTextLength: document.body.textContent.length
        }});
      } catch (e) {
        sendResponse({ success: false, error: e.message });
      }
    })();
  }
  return true;
});
