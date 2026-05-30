// Popup logic — manages scrape queue and sends to server

let queue = [];

document.addEventListener('DOMContentLoaded', async () => {
  // Load saved state
  const stored = await chrome.storage.local.get(['queue', 'serverUrl']);
  queue = stored.queue || [];
  if (stored.serverUrl) document.getElementById('server-url').value = stored.serverUrl;
  renderQueue();

  document.getElementById('btn-scrape').addEventListener('click', () => scrapeCurrentTab(false));
  document.getElementById('btn-scrape-send').addEventListener('click', () => scrapeCurrentTab(true));
  document.getElementById('btn-send-all').addEventListener('click', sendAllToServer);
  document.getElementById('btn-clear').addEventListener('click', clearQueue);
  document.getElementById('btn-test').addEventListener('click', testConnection);
  document.getElementById('btn-debug').addEventListener('click', debugCurrentTab);
  document.getElementById('btn-debug-reviews').addEventListener('click', debugReviews);
});

function setStatus(msg, isError) {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.style.color = isError ? '#dc3545' : '#666';
}

function getServerUrl() {
  const url = document.getElementById('server-url').value.trim().replace(/\/$/, '');
  chrome.storage.local.set({ serverUrl: url });
  return url;
}

async function scrapeCurrentTab(sendImmediately) {
  setStatus('Scraping...');
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab.url.includes('shopee.vn')) {
      setStatus('Not a Shopee page!', true);
      return;
    }

    // Inject content script if not already there
    try {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ['content.js']
      });
    } catch (e) {
      // Already injected, ignore
    }

    const response = await chrome.tabs.sendMessage(tab.id, { action: 'scrape' });
    if (!response || !response.success) {
      setStatus('Scrape failed: ' + (response?.error || 'no response'), true);
      return;
    }

    const data = response.data;
    // Check if already in queue (by URL)
    const existing = queue.findIndex(q => q.url === data.url);
    if (existing >= 0) {
      queue[existing] = { ...data, status: 'ready' };
      setStatus('Updated: ' + (data.title || data.url).substring(0, 40));
    } else {
      queue.push({ ...data, status: 'ready' });
      setStatus('Added: ' + (data.title || data.url).substring(0, 40));
    }

    await saveQueue();
    renderQueue();

    if (sendImmediately) {
      await sendOne(queue.length - 1);
    }
  } catch (e) {
    setStatus('Error: ' + e.message, true);
  }
}

async function sendAllToServer() {
  const serverUrl = getServerUrl();
  if (!serverUrl) { setStatus('Set server URL first', true); return; }

  const pending = queue.filter(q => q.status === 'ready' || q.status === 'error');
  if (!pending.length) { setStatus('Nothing to send'); return; }

  setStatus(`Sending ${pending.length} products...`);
  let sent = 0;

  for (let i = 0; i < queue.length; i++) {
    if (queue[i].status !== 'ready' && queue[i].status !== 'error') continue;
    await sendOne(i);
    sent++;
    setStatus(`Sent ${sent}/${pending.length}...`);
  }

  setStatus(`Done! ${sent} products sent.`);
}

async function sendOne(idx) {
  const serverUrl = getServerUrl();
  const item = queue[idx];
  if (!item) return;

  queue[idx].status = 'sending';
  renderQueue();

  try {
    const payload = {
      url: item.url,
      title: item.title,
      price: item.price,
      description: item.description,
      rating: item.rating,
      rating_count: item.rating_count,
      sold_count: item.sold_count,
      reviews: item.reviews || [],
    };

    const resp = await fetch(serverUrl + '/receive-shopee-data', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    queue[idx].status = 'done';
  } catch (e) {
    queue[idx].status = 'error';
    queue[idx].error = e.message;
  }

  await saveQueue();
  renderQueue();
}

async function testConnection() {
  const serverUrl = getServerUrl();
  try {
    const resp = await fetch(serverUrl + '/poll-shopee-data', { method: 'GET' });
    if (resp.ok) setStatus('Connected to server ✓');
    else setStatus('Server returned ' + resp.status, true);
  } catch (e) {
    setStatus('Cannot reach server: ' + e.message, true);
  }
}

async function debugCurrentTab() {
  setStatus('Debugging selectors...');
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    try {
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] });
    } catch (e) {}
    const response = await chrome.tabs.sendMessage(tab.id, { action: 'debug' });
    if (response?.success) {
      const d = response.data;
      let msg = 'PRICE:\n' + (d.priceCandidates.length ? d.priceCandidates.map(c => `  ${c.tag}.${c.class.split(' ')[0]} = "${c.text}"`).join('\n') : '  (none found)');
      msg += '\n\nRATING COUNT:\n' + (d.ratingCandidates.length ? d.ratingCandidates.map(c => `  ${c.tag}.${c.class.split(' ')[0]} = "${c.text}"`).join('\n') : '  (none found)');
      msg += '\n\nSOLD:\n' + (d.soldCandidates.length ? d.soldCandidates.map(c => `  ${c.tag}.${c.class.split(' ')[0]} = "${c.text}"`).join('\n') : '  (none found)');
      msg += `\n\nREVIEW TABS (${d.reviewTabCandidates?.length || 0}):\n` + (d.reviewTabCandidates?.length ? d.reviewTabCandidates.map(c => `  ${c.tag}.${c.class?.split(' ')[0] || ''} [${c.children}ch] = "${c.text}" parent=${c.parent}`).join('\n') : '  (none)');
      msg += `\n\nREVIEW CONTENT (selector hits: ${d.reviewCount || 0}):\n` + (d.reviewTextCandidates?.length ? d.reviewTextCandidates.map(c => `  ${c.tag}.${c.class?.split(' ')[0] || ''} = "${c.text}" parent=${c.parent}`).join('\n') : '  (none found)');
      // Show in a pre-formatted way
      const list = document.getElementById('queue-list');
      list.innerHTML = '<pre style="font-size:10px;white-space:pre-wrap;background:#f4f4f4;padding:8px;border-radius:6px">' + msg + '</pre>';
      setStatus('Debug done — see below');
    } else {
      setStatus('Debug failed: ' + (response?.error || 'no response'), true);
    }
  } catch (e) {
    setStatus('Error: ' + e.message, true);
  }
}

async function debugReviews() {
  setStatus('Scrolling + clicking review tab...');
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    try {
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] });
    } catch (e) {}
    const response = await chrome.tabs.sendMessage(tab.id, { action: 'debug-reviews' });
    if (response?.success) {
      const d = response.data;
      let msg = `CLICKED: ${d.clickedBtn ? d.clickedBtn.text + ' (' + d.clickedBtn.class + ')' : 'NONE'}`;
      msg += `\nPage: ${d.pageHeight}px height, ${d.bodyTextLength} chars`;
      msg += `\n\nAVATAR IMAGES (${d.avatarImgs?.length || 0}):\n`;
      msg += (d.avatarImgs || []).map(c => `  ${c.src}\n    parent=${c.parent} gp=${c.grandparent}`).join('\n') || '  (none)';
      msg += `\n\nREPEATED STRUCTURES (${d.repeatedStructures?.length || 0}):\n`;
      msg += (d.repeatedStructures || []).map(c => `  .${c.parentClass} [${c.childCount}x .${c.childClass}]\n    "${c.sampleText}"`).join('\n') || '  (none)';
      msg += `\n\nBOTTOM TEXT:\n${d.bottomText?.substring(0, 300) || '(empty)'}`;
      const list = document.getElementById('queue-list');
      list.innerHTML = '<pre style="font-size:10px;white-space:pre-wrap;background:#f4f4f4;padding:8px;border-radius:6px">' + msg + '</pre>';
      setStatus('Review debug done');
    } else {
      setStatus('Debug failed: ' + (response?.error || 'no response'), true);
    }
  } catch (e) {
    setStatus('Error: ' + e.message, true);
  }
}

async function clearQueue() {
  queue = [];
  await saveQueue();
  renderQueue();
  // Also clear server-side queue
  const serverUrl = getServerUrl();
  if (serverUrl) {
    try {
      await fetch(serverUrl + '/clear-shopee-queue', { method: 'POST' });
    } catch (e) {}
  }
  setStatus('Queue cleared');
}

async function saveQueue() {
  await chrome.storage.local.set({ queue });
}

function renderQueue() {
  const list = document.getElementById('queue-list');
  document.getElementById('queue-count').textContent = queue.length;

  if (!queue.length) {
    list.innerHTML = '<div style="color:#999;text-align:center;padding:12px">No products yet. Open a Shopee product page and click "Scrape".</div>';
    return;
  }

  list.innerHTML = queue.map((item, i) => {
    const title = (item.title || item.url || '').substring(0, 45);
    const revs = (item.reviews || []).length;
    const rating = item.rating ? '⭐' + item.rating : '';
    let badge = '';
    if (item.status === 'done') badge = '<span class="badge badge-ok">✓</span>';
    else if (item.status === 'error') badge = '<span class="badge badge-err" title="' + (item.error || '') + '">✗</span>';
    else if (item.status === 'sending') badge = '<span class="badge badge-wait">...</span>';
    else badge = '<span class="badge badge-wait">⏳</span>';

    return `<div class="queue-item ${item.status}">
      <span class="title">${i + 1}. ${title}</span>
      <span style="font-size:10px;color:#666;margin:0 4px">${revs}💬 ${rating}</span>
      ${badge}
    </div>`;
  }).join('');
}
