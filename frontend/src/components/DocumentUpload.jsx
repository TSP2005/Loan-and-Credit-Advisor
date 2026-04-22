import { useState, useRef } from 'react';
import { apiUpload, sendLog } from '../api/client';

export default function DocumentUpload({ userId, token, onUploadComplete }) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const fileRef = useRef(null);

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) uploadFile(file);
  };

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file) uploadFile(file);
  };

  const uploadFile = async (file) => {
    setUploading(true);
    setResult(null);
    sendLog('info', 'DocumentUpload', 'UPLOAD_STARTED', `file=${file.name} size=${file.size}`);
    try {
      const data = await apiUpload('/documents/upload', file, token);
      setResult(data);
      sendLog('info', 'DocumentUpload', 'UPLOAD_SUCCESS', `file=${file.name}`);
      if (onUploadComplete) onUploadComplete();
    } catch (err) {
      setResult({ success: false, error: err.message });
      sendLog('error', 'DocumentUpload', 'UPLOAD_FAILED', err.message);
    }
    setUploading(false);
  };

  return (
    <div>
      <div
        className={`upload-zone ${isDragOver ? 'dragover' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileRef.current?.click()}
        id="upload-zone"
      >
        <div className="upload-icon">📄</div>
        <p>{uploading ? '⏳ Uploading...' : isDragOver ? 'Drop file here' : 'Drag & drop a document, or click to browse'}</p>
        <p className="upload-hint">Supports PDF, TXT files (salary slips, tax forms, etc.)</p>
        <input ref={fileRef} type="file" accept=".pdf,.txt,.doc,.docx" style={{ display: 'none' }}
          onChange={handleFileSelect} id="file-upload-input" />
      </div>

      {result && (
        <div className="glass-card" style={{ marginTop: 'var(--spacing-md)' }}>
          {result.success ? (
            <>
              <p style={{ color: 'var(--success)', fontWeight: 600 }}>✅ Document processed successfully</p>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: 'var(--spacing-sm)' }}>
                File: {result.file} ({(result.size_bytes / 1024).toFixed(1)} KB)
              </p>
              {result.extraction?.extracted_fields && Object.keys(result.extraction.extracted_fields).length > 0 && (
                <div style={{ marginTop: 'var(--spacing-md)' }}>
                  <p style={{ fontWeight: 600, fontSize: '0.9rem' }}>Extracted Information:</p>
                  {Object.entries(result.extraction.extracted_fields).map(([key, val]) => (
                    <div className="profile-stat" key={key}>
                      <span className="label">{key.replace(/_/g, ' ')}</span>
                      <span className="value">{typeof val === 'number' ? `₹${val.toLocaleString()}` : val}</span>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p style={{ color: 'var(--danger)' }}>❌ {result.error || 'Upload failed'}</p>
          )}
        </div>
      )}
    </div>
  );
}
