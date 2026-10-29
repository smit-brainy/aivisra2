import React, { useEffect, useState } from 'react';
import { invr, merged } from '../../prototype/api';

export default function OnboardingPage({ session, openSearch, navTo }) {
  const admin = session.role === 'admin';
  const I = invr();
  const M = merged('day', {});
  const CAM = M.CAM;
  const cams = M.cams || [];
  const SCEN = M.SCEN?.day || { now: 40800, offline: {}, gaps: {}, space: { pct: '84%', kept: '38 GB', recv: '241 GB' } };

  // Sample cameras from INVR data (mirroring prototype's 16 cameras)
  const sampleCameras = [
    { id: 1, name: 'Main gate entry', area: 'Gates and fence', status: 'online', level: 'standard', kind: 'person' },
    { id: 2, name: 'Main gate exit', area: 'Gates and fence', status: 'online', level: 'standard', kind: 'vehicle' },
    { id: 3, name: 'Lobby corridor', area: 'Office', status: 'online', level: 'standard', kind: 'person' },
    { id: 4, name: 'Reception', area: 'Office', status: 'online', level: 'standard', kind: 'person' },
    { id: 5, name: 'Visitor parking', area: 'Parking', status: 'online', level: 'standard', kind: 'car' },
    { id: 6, name: 'Staff parking', area: 'Parking', status: 'online', level: 'standard', kind: 'motorbike' },
    { id: 7, name: 'Dock 1', area: 'Warehouse', status: 'online', level: 'standard', kind: 'truck' },
    { id: 8, name: 'Dock 2', area: 'Warehouse', status: 'online', level: 'standard', kind: '' },
    { id: 9, name: 'Stores', area: 'Warehouse', status: 'online', level: 'standard', kind: 'person' },
    { id: 10, name: 'Line A', area: 'Production', status: 'online', level: 'standard', kind: 'person' },
    { id: 11, name: 'Line B', area: 'Production', status: 'online', level: 'standard', kind: 'person' },
    { id: 12, name: 'Packing', area: 'Warehouse', status: 'online', level: 'standard', kind: 'person' },
    { id: 13, name: 'Back gate', area: 'Gates and fence', status: 'offline', level: 'standard', kind: '' },
    { id: 14, name: 'Stairwell 2', area: 'Office', status: 'online', level: 'standard', kind: 'person' },
    { id: 15, name: 'Server room door', area: 'Office', status: 'online', level: 'standard', kind: 'person' },
    { id: 16, name: 'North fence', area: 'Gates and fence', status: 'online', level: 'standard', kind: 'person' },
  ];

  // State for the onboarding flow
  const [step, setStep] = useState('choose'); // choose | scan | credentials | connect | confirm | done
  const [selectedCamera, setSelectedCamera] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState(0);
  const [foundCameras, setFoundCameras] = useState([]);
  const [tickedCameras, setTickedCameras] = useState([]);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [credError, setCredError] = useState(false);
  const [detailLevel, setDetailLevel] = useState('standard');
  const [confirmCameras, setConfirmCameras] = useState([]);
  const [showChecklist, setShowChecklist] = useState(false);

  // Initialize - load camera data
  useEffect(() => {
    if (!I) return;
    setFoundCameras(cams.map(c => ({
      id: c.num,
      model: c.name,
      label: c.label,
      area: c.areaName || c.area,
      status: c.status || 'online',
      kind: c.boxes?.[0]?.[0]?.kind || 'person',
    })));
  }, [I, cams]);

  // Mock scan progress
  const startScan = () => {
    setScanning(true);
    setScanProgress(0);
    const timer = setInterval(() => {
      setScanPrev(prev => Math.min(prev + 10, 100));
      if (scanProgress >= 100) {
        clearInterval(timer);
        setScanning(false);
        setFoundCameras(sampleCameras.map(c => ({
          id: c.num,
          model: c.name,
          label: c.label,
          area: c.areaName || c.area,
          status: c.status,
          kind: c.boxes?.[0]?.[0]?.kind || 'person',
        })));
        setTickedCameras([]);
      }
    }, 200);
    // Cleanup after 5 seconds
    const cleanup = setTimeout(() => {
      clearInterval(timer);
      setScanning(false);
      setFoundCameras(sampleCameras.map(c => ({
        id: c.num,
        model: c.name,
        label: c.label,
        area: c.areaName || c.area,
        status: c.status,
        kind: c.boxes?.[0]?.[0]?.kind || 'person',
      })));
      setTickedCameras([]);
    }, 5000);
    return () => {
      clearInterval(timer);
      clearTimeout(cleanup);
    };
  };

  // Mock credential validation
  const validateCreds = () => {
    // In prototype, credentials are checked against camera firmware
    // Here we just validate non-empty fields
    if (!username || !password) {
      setCredError(true);
      return false;
    }
    setCredError(false);
    return true;
  };

  // Mock camera connection
  const connectCamera = (cam) => ({
    ...cam,
    connected: true,
    tested: true,
    status: 'online',
    picture: 'https://via.placeholder.com/320x240?text=Camera+'+cam.id,
  });

  // Render checklist (from prototype home template)
  const renderChecklist = () => (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 4fr) minmax(0, 8fr)', gap: '40px', padding: '24px 28px', background: 'var(--bone)', border: '1px solid var(--line)', borderRadius: '14px' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        <span style={{ font: '500 11px/1.3 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--muted)' }}>Set up i-Netra</span>
        <h2 style={{ margin: '0', fontSize: '26px', fontWeight: '500', letterSpacing: '-0.025em', lineHeight: '1.15' }}>Checklist</h2>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ width: '7px', height: '7px', marginTop: '7px', borderRadius: '50%', background: 'var(--info-deep)' }} />
          <span style={{ flex: '1', minWidth: '260', fontSize: '15' }}> <strong style={{ fontWeight: '600' }}>Import live video from cameras</strong> </span>
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ width: '7px', height: '7px', marginTop: '7px', borderRadius: '50%', background: 'var(--success)' }} />
          <span>Add your first camera</span>
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ width: '7px', height: '7px', marginTop: '7px', borderRadius: '50%', background: 'var(--info-deep)' }} />
          <span>Set up recording retention</span>
        </span>
      </div>
    </div>
  );

  // Render choose step
  const renderChoose = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20', padding: '24px 32px 32px' }}>
      <h1>Get cameras working</h1>
      <p>Pick the way that suits what you have. Each one ends the same way: you see every new camera's picture, give it a name and an area, and choose its detail level.</p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', maxWidth: '1100px' }}>
        {/* Scan way */}
        <div style={{ 
          display: 'grid', gridTemplateColumns: '48px minmax(0,1fr) auto', gap: '18px', 
          alignItems: 'center', padding: '22px 8px 22px 4px', borderBottom: '1px solid var(--line)', 
          background: 'var(--bone)', cursor: 'pointer', marginBottom: '8px'
        }} onClick={() => setStep('scan')}>
          <span style={{ font: '500 14px/1 var(--font-mono)', color: 'var(--muted)' }}>1</span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', minWidth: '0' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>Scan your network</span>
            <span style={{ fontSize: '18', color: 'var(--muted)' }}>Next</span>
          </div>
        </div>
        {/* Address way */}
        <div style={{ 
          display: 'grid', gridTemplateColumns: '48px minmax(0,1fr) auto', gap: '18px', 
          alignItems: 'center', padding: '22px 8px 22px 4px', borderBottom: '1px solid var(--line)', 
          background: 'var(--bone)', cursor: 'pointer', marginBottom: '8px'
        }} onClick={() => setStep('credentials')}>
          <span style={{ font: '500 14px/1 var(--font-mono)', color: 'var(--muted)' }}>2</span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', minWidth: '0' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '10x' }}>Enter camera address</span>
            <span style={{ fontSize: '18', color: 'var(--muted)' }}>Next</span>
          </div>
        </div>
        {/* Recorder way */}
        <div style={{ 
          display: 'grid', gridTemplateColumns: '48px minmax(0,1fr) auto', gap: '18px', 
          alignItems: 'center', padding: '22px 8px 22px 4px', borderBottom: '1px solid var(--line)', 
          background: 'var(--bone)', cursor: 'pointer', marginBottom: '8px'
        }} onClick={() => setStep('connect')}>
          <span style={{ font: '500 14px/1 var(--font-mono)', color: 'var(--muted)' }}>3</span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', minWidth: '0' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '10x' }}>Use site recorder</span>
            <span style={{ fontSize: '18', color: 'var(--muted)' }}>Next</span>
          </div>
        </div>
        {/* Upload way */}
        <div style={{ 
          display: 'grid', gridTemplateColumns: '48px minmax(0,1fr) auto', gap: '18px', 
          alignItems: 'center', padding: '22px 8px 22px 4px', borderBottom: '1px solid var(--line)', 
          background: 'var(--bone)', cursor: 'pointer'
        }}>
          <span style={{ font: '500 14px/1 var(--font-mono)', color: 'var(--muted)' }}>4</span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', minWidth: '0' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '10x' }}>Upload camera list</span>
            <span style={{ fontSize: '18', color: 'var(--muted)' }}>Next</span>
          </div>
        </div>
      </div>
    </div>
  );

  // Render scan step
  const renderScan = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20', padding: '24px 32px 32px' }}>
      <h2>Looking for cameras on this network…</h2>
      {scanning && (
        <div style={{ height: '6px', borderRadius: '3px', background: 'var(--paper-3)', overflow: 'hidden', marginBottom: '16px' }}>
          <div style={{ width: scanProgress, height: '100%', background: '#1976d2', borderRadius: '3px' }} />
        </div>
      )}
      <span style={{ fontSize: '13', color: 'var(--muted)' }}>{scanning ? 'Scanning…' : 'No cameras found'}</span>
      {(!scanning || scanProgress >= 100) && (
        <div style={{ marginTop: '16px' }}>
          <button onClick={() => startScan()} style={{ padding: '10px 16px', border: '1px solid var(--line)', borderRadius: '8', background: 'var(--paper)', color: 'var(--ink)', fontSize: '14', cursor: 'pointer' }}>
            {scanning ? 'Scanning…' : 'Look again'}
          </button>
        </div>
      )}
      {foundCameras.length > 0 && (
        <div style={{ marginTop: '24px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <span style={{ fontSize: '13', color: 'var(--muted)' }}>Found {foundCameras.length} cameras</span>
          {foundCameras.map((cam) => (
            <div key={cam.id} style={{ 
              display: 'grid', gridTemplateColumns: '20px minmax(0,1fr) auto', gap: '14px', 
              alignItems: 'center', minHeight: '60px', padding: '8px 18px', 
              borderBottom: '1px solid var(--line-soft)', background: 'var(--paper)', cursor: 'pointer'
            }} onClick={() => setSelectedCamera(cam)}>
              <span style={{ width: '20', height: '20', borderRadius: '4', border: '1.5px solid ' + (cam.status === 'online' ? '#4caf50' : '#f44336'), background: cam.status === 'online' ? '#4caf50' : '#f44336', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: '700', color: 'var(--paper)' }}>
                {cam.id}
              </span>
              <span style={{ display: 'flex', flexDirection: 'column', gap: '2' }}>
                <span style={{ fontSize: '15.5', fontWeight: '500' }}>{cam.label}</span>
                <span style={{ fontSize: '13.5', color: 'var(--muted)' }}>{cam.area}</span>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  // Render credentials step
  const renderCredentials = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20', padding: '24px 32px 32px' }}>
      <h2>Type the username and password set on the cameras</h2>
      <p>i-Netra tries them on all {tickedCameras.length} at once.</p>
      {credError && (
        <span style={{ marginTop: '-8', fontSize: '14', color: 'var(--danger-deep)' }}>Type the cameras' password to carry on.</span>
      )}
      <div style={{ maxWidth: '560', display: 'flex', flexDirection: 'column', gap: '18px' }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: '6' }}>
          <span style={{ fontSize: '14', fontWeight: '500' }}>Camera username</span>
          <input 
            value={username} 
            onChange={e => setUsername(e.target.value)} 
            spellcheck="false" 
            style={{ height: '52', padding: '0 14', border: '1px solid var(--line)', borderRadius: '8', background: 'var(--paper)', fontSize: '16', outline: 'none' }}
            styleFocus={{ borderColor: 'var(--blue)', boxShadow: '0 0 0 3px var(--blue-tint)' }}
          />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: '6' }}>
          <span style={{ fontSize: '14', fontWeight: '500' }}>Camera password</span>
          <input 
            type="password" 
            value={password} 
            onChange={e => setPassword(e.target.value)} 
            placeholder="The password set on the cameras" 
            style={{ height: '52', padding: '0 14', border: '1px solid var(--line)', borderRadius: '8', background: 'var(--paper)', fontSize: '16', outline: 'none' }}
            styleFocus={{ borderColor: 'var(--blue)', boxShadow: '0 0 0 3px var(--blue-tint)' }}
          />
        </label>
        {!credError && (
          <span style={{ fontSize: '14', color: 'var(--muted)' }}>A camera with a different password can be fixed on its own in the next step.</span>
        )}
      </div>
    </div>
  );

  // Render connect step
  const renderConnect = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20', padding: '24px 32px 32px' }}>
      <h2>Connecting cameras through the site's recorder</h2>
      <p>i-Netra reads these cameras through the site's recorder, so there's no camera password to type.</p>
      {selectedCamera && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: '14', overflow: 'hidden' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '160', background: 'var(--bone)', borderBottom: '1px solid var(--line)' }}>
            <span style={{ fontSize: '48', color: 'var(--muted)' }}>{selectedCamera.id}</span>
          </div>
          <div style={{ padding: '16px', color: 'var(--ink)' }}>
            <span style={{ fontSize: '14', fontWeight: '500' }}>Model: {selectedCamera.model}</span>
            <span style={{ fontSize: '14', color: 'var(--muted)' }}>Area: {selectedCamera.area}</span>
            <span style={{ fontSize: '14', color: 'var(--muted)' }}>Status: {selectedCamera.status}</span>
          </div>
          <button onClick={() => setStep('confirm')} style={{ padding: '12px 24px', border: '1px solid var(--line)', borderRadius: '8', background: 'var(--paper)', color: 'var(--ink)', fontSize: '14', fontWeight: '500' }}>
            Continue to confirmation
          </button>
        </div>
      )}
    </div>
  );

  // Render confirm step
  const renderConfirm = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20', padding: '24px 32px 32px' }}>
      <h2>Confirm camera details</h2>
      <p>Give each new camera a name, choose its area, and select its detail level.</p>
      {selectedCamera && (
        <div style={{ background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: '14', overflow: 'hidden' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px', padding: '16px', borderBottom: '1px solid var(--line)' }}>
            <div style={{ aspectRatio: '16/9', borderRadius: '8', background: 'var(--bone)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <span style={{ color: 'var(--muted)', fontSize: '12' }}>Live picture</span>
            </div>
            <div>
              <span style={{ fontSize: '15.5', fontWeight: '500' }}>{selectedCamera.label}</span>
              <span style={{ fontSize: '13.5', color: 'var(--muted)' }}>(Camera {selectedCamera.id})</span>
            </div>
          </div>
          <div style={{ padding: '16px' }}>
            <div style={{ display: 'flex', gap: '16px', marginBottom: '16px' }}>
              <span style={{ fontSize: '13', color: 'var(--muted)' }}>Name</span>
              <input 
                value={selectedCamera.label} 
                onChange={e => { /* update label */ }} 
                style={{ padding: '8px', border: '1px solid var(--line)', borderRadius: '6', fontSize: '14' }}
              />
              <span style={{ fontSize: '13', color: 'var(--muted)' }}>Area</span>
              <select style={{ padding: '8px', border: '1px solid var(--line)', borderRadius: '6', fontSize: '14' }}>
                <option value='Gates and fence'>Gates and fence</option>
                <option value='Office'>Office</option>
                <option value='Parking'>Parking</option>
                <option value='Warehouse'>Warehouse</option>
                <option value='Production'>Production</option>
              </select>
            </div>
            <div style={{ display: 'flex', gap: '16px' }}>
              <span style={{ fontSize: '13', color: 'var(--muted)' }}>Detail level</span>
              <select style={{ padding: '8px', border: '1px solid var(--line)', borderRadius: '6', fontSize: '14' }}>
                <option value='low'>Low</option>
                <option value='standard' selected>Standard</option>
                <option value='high'>High</option>
                <option value='maximum'>Maximum</option>
              </select>
            </div>
          </div>
          <div style={{ display: 'flex', justifyContent: 'flexEnd', padding: '16px' }}>
            <button onClick={() => setStep('done')} style={{ padding: '10px 24px', border: '1px solid var(--line)', borderRadius: '8', background: 'var(--ink)', color: 'var(--paper)', fontSize: '14', fontWeight: '500' }}>
              Add cameras
            </button>
          </div>
        </div>
      )}
    </div>
  );

  // Render done step
  const renderDone = () => {
    // Count added cameras
    const addedCount = confirmCameras.length;
    
    return (
      <div style={{ maxWidth: '820', margin: '40px auto 0', display: 'flex', flexDirection: 'column', alignItems: 'flexStart', gap: '18px' }}>
        <span style={{ display: 'flex', gap: '10', font: '500 11px/1.3 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--success-deep)' }}>
          <span style={{ width: '8', height: '8', borderRadius: '50', background: 'var(--success)' }} />
          Done
        </span>
        <h2 style={{ margin: '0', fontSize: '56', fontWeight: '500', letterSpacing: '-0.035em', lineHeight: '1' }}>Added {addedCount} cameras</h2>
        <p style={{ margin: '0', fontSize: '19', color: 'var(--muted)' }}>They now appear on Home and in Live view.</p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6', margin: '4px 0 10px' }}>
          {confirmCameras.slice(0, 4).map((cam, i) => (
            <span key={i} style={{ display: 'flex', gap: '8', height: '34', padding: '0 12', borderRadius: '4', background: 'var(--paper-2)', fontSize: '14' }}>
              <span style={{ font: '500 12px/1 var(--font-mono)', color: 'var(--muted)' }}>{cam.num}</span>{cam.name}
            </span>
          ))}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '12' }}>
          <button style={{ padding: '14px 24px', border: '1px solid var(--line)', borderRadius: '8', background: 'var(--paper)', fontSize: '14', fontWeight: '500', styleHover: 'border-color: var(--ink)' }}>
            Go to Live view
          </button>
          <button style={{ padding: '14px 20px', border: '1px solid var(--line)', borderRadius: '999', fontSize: '15', fontWeight: '500', styleHover: 'border-color: var(--ink)' }}>Add more</button>
        </div>
      </div>
    );
  };

  // Render based on step
  if (step === 'choose') return renderChoose();
  if (step === 'scan') return renderScan();
  if (step === 'credentials') return renderCredentials();
  if (step === 'connect') return renderConnect();
  if (step === 'confirm') return renderConfirm();
  if (step === 'done') return renderDone();

  return null;
}