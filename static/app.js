const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const browseBtn = document.getElementById('browse-btn');
const uploadStatus = document.getElementById('upload-status');
const resultsSection = document.getElementById('results-section');
const fileDetails = document.getElementById('file-details');
const featuresBody = document.getElementById('features-body');

let pollInterval;

browseBtn.addEventListener('click', () => fileInput.click());

['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, preventDefaults, false);
});
function preventDefaults(e) { e.preventDefault(); e.stopPropagation(); }

['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, () => dropZone.classList.add('dragover'), false);
});
['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, () => dropZone.classList.remove('dragover'), false);
});

dropZone.addEventListener('drop', (e) => {
    let dt = e.dataTransfer;
    let files = dt.files;
    handleFiles(files);
});

fileInput.addEventListener('change', function() {
    handleFiles(this.files);
});

function setStatus(msg, type) {
    uploadStatus.innerHTML = msg;
    uploadStatus.className = `status-msg ${type}`;
    uploadStatus.classList.remove('hidden');
}

function handleFiles(files) {
    if (files.length === 0) return;
    const file = files[0];
    
    resultsSection.classList.add('hidden');
    clearInterval(pollInterval);
    
    uploadFile(file);
}

async function uploadFile(file) {
    setStatus(`Uploading <b>${file.name}</b> <br><small>This may take a moment...</small>`, 'info');
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch('/api/files/', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || 'Upload failed');
        }
        
        setStatus('Upload Success! Processing Geometry...', 'info');
        pollStatus(data.id);
        
    } catch (error) {
        setStatus(`Error: ${error.message}`, 'error');
    }
}

function pollStatus(fileId) {
    pollInterval = setInterval(async () => {
        try {
            const res = await fetch(`/api/files/${fileId}/`);
            const data = await res.json();
            
            if (data.status === 'COMPLETED') {
                clearInterval(pollInterval);
                setStatus('Analysis Completed Successfully!', 'success');
                displayResults(fileId);
            } else if (data.status === 'FAILED') {
                clearInterval(pollInterval);
                setStatus(`Processing Failed: ${data.error}`, 'error');
            }
        } catch (error) {
            clearInterval(pollInterval);
            setStatus('Network error checking status.', 'error');
        }
    }, 1000);
}

async function displayResults(fileId) {
    try {
        const resInfo = await fetch(`/api/files/${fileId}/`);
        const info = await resInfo.json();
        
        const resMeas = await fetch(`/api/files/${fileId}/measurements/`);
        const measData = await resMeas.json();
        
        renderFileInfo(info);
        renderFeatures(measData.features);
        
        resultsSection.classList.remove('hidden');
        renderMap(measData.features);
    } catch (error) {
        setStatus('Failed to load final measurements.', 'error');
    }
}

function renderFileInfo(info) {
    fileDetails.innerHTML = `
        <div class="detail-item">
            <span class="detail-label">File</span>
            <span class="detail-value">${info.filename}</span>
        </div>
        <div class="detail-item">
            <span class="detail-label">Features</span>
            <span class="detail-value">${info.feature_count} geometries</span>
        </div>
        <div class="detail-item">
            <span class="detail-label">CRS Target</span>
            <span class="detail-value" style="font-size: 1rem;">${info.crs}</span>
        </div>
        <div class="detail-item">
            <span class="detail-label">Status</span>
            <span class="detail-value" style="color:var(--success)">${info.status}</span>
        </div>
    `;
}

function renderFeatures(features) {
    featuresBody.innerHTML = '';
    
    // Sort array safely if applicable or just iterate max 500 features to prevent UI lock
    const cappedFeatures = features.slice(0, 500); 
    
    cappedFeatures.forEach(f => {
        const tr = document.createElement('tr');
        
        let propsHTML = '';
        if (f.properties) {
            const keys = Object.keys(f.properties);
            // Show only first 3 properties for neatness, hide rest or limit
            for(let i=0; i<Math.min(keys.length, 4); i++) {
                const k = keys[i];
                let v = f.properties[k];
                if (v && v.length > 20) v = v.substring(0, 18) + '...';
                if (v && v.trim() !== '' && v !== 'None' && v != 'nan') {
                   propsHTML += `<span class="prop-badge">${k}: ${v}</span>`;
                }
            }
            if(keys.length > 4) propsHTML += `<span class="prop-badge">...</span>`;
        }
        
        let mVal = f.measurement.value;
        let mStr = '-';
        if (mVal !== 0 && mVal) {
            // Formatting large numbers with commas
            const formatted = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(mVal);
            mStr = `<span style="color:var(--accent); font-weight:600;">${formatted} ${f.measurement.unit}</span>`;
        } else if (f.measurement.message) {
            mStr = `<span style="opacity:0.6;font-size:0.8rem">${f.measurement.message}</span>`;
        }
        
        tr.innerHTML = `
            <td>#${f.feature_id}</td>
            <td><strong>${f.geometry_type}</strong></td>
            <td>${mStr}</td>
            <td>${propsHTML || '<span style="opacity:0.5">No metrics</span>'}</td>
        `;
        featuresBody.appendChild(tr);
    });
}

let map = null;

function renderMap(features) {
    if (!map) {
        map = L.map('map', {zoomControl: true}).setView([0, 0], 2);
        // Using CartoDB Dark Matter tile layer for an elegant dark map
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
            subdomains: 'abcd',
            maxZoom: 20
        }).addTo(map);
    }
    
    // Clear old geojson layers if you upload a new file
    map.eachLayer(layer => {
        if (layer.feature) {
            map.removeLayer(layer);
        }
    });

    const geoData = {
        type: "FeatureCollection",
        features: features.map(f => ({
            type: "Feature",
            geometry: f.geometry,
            properties: f.properties || {}
        }))
    };
    
    const geoJsonLayer = L.geoJSON(geoData, {
        style: {
            color: '#00e5ff',
            weight: 1.5,
            opacity: 0.8,
            fillOpacity: 0.15
        },
        onEachFeature: (feature, layer) => {
            if (feature.properties) {
                const keys = Object.keys(feature.properties);
                if (keys.length > 0) {
                    const firstKey = keys[0]; // Just show an identifier on click
                    layer.bindPopup(`<b style="color: black;">${firstKey}:</b> <span style="color: #333">${feature.properties[firstKey]}</span>`);
                }
            }
        }
    }).addTo(map);
    
    // Fit viewport to bounding box of the geometries
    if(features.length > 0) {
        try {
            map.fitBounds(geoJsonLayer.getBounds());
            // Delay rendering adjustment by 400ms to allow CSS unhide animations to resolve perfectly
            setTimeout(() => map.invalidateSize(), 400); 
        } catch(e) {}
    }
}
