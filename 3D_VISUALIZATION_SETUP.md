# 3D Visualization Setup Guide

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd apps/web
npm install
```

### 2. Start the Services

```bash
# Terminal 1: Start API
cd services/api
python main.py

# Terminal 2: Start Web with 3D Visualization
cd apps/web
npm run dev
```

### 3. Access the Application

- **Main Dashboard**: http://localhost:3000
- **3D Laboratory**: http://localhost:3000/visualization

## 🎮 Using the 3D Laboratory

### Navigation Controls
- **Left Mouse**: Rotate camera around the lab
- **Right Mouse**: Pan camera position
- **Scroll Wheel**: Zoom in/out
- **Click Instruments**: Interact with equipment

### Features Available

#### 1. Laboratory Environment
- Realistic workbench with power outlets
- Fume hood with movable glass sash
- Safety shower (click to activate)
- Multiple instruments

#### 2. Interactive Instruments
- **Potentiostat**: Click power button to turn on/off
- **Analytical Balance**: Shows weight readings
- **Peristaltic Pump**: Click to start/stop pumping

#### 3. Electrochemical Cell Visualization
- Glass beaker with electrolyte
- Three-electrode system (working, counter, reference)
- Real-time bubble generation based on current
- Deposition layer visualization

#### 4. Volume Rendering
- Concentration field visualization
- GPU-accelerated ray marching
- Multiple color maps (viridis, plasma, coolwarm)
- Adjustable opacity and threshold

### Starting an Experiment

1. **Create a Run** from the main dashboard
2. **Go to 3D Laboratory** (click "3D Laboratory" button)
3. **Select the Run** from the dropdown in the control panel
4. **Watch Real-time Updates**:
   - Current density changes
   - Concentration gradients
   - Bubble formation
   - Deposition growth

## 🛠️ Technical Details

### Component Structure

```
components/visualization/
├── LabCanvas.tsx        # Main 3D scene container
├── Laboratory.tsx       # Lab environment (floor, walls, workbench)
├── ElectrochemicalCell.tsx  # Beaker with electrodes
├── VolumeField.tsx      # Volume rendering for concentration
├── Instruments.tsx      # Interactive lab instruments
└── LoadingScreen.tsx    # Loading indicator

hooks/
└── useSimulationData.ts # Real-time data streaming hook
```

### Performance Settings

The visualization supports three quality levels:

- **Low**: Reduced resolution, no post-processing
- **Medium**: Standard quality with SSAO
- **High**: Full resolution with all effects

### Data Flow

1. **API** generates simulation data
2. **SSE/WebSocket** streams updates to client
3. **React hooks** manage state and updates
4. **Three.js** renders 3D scene
5. **Shaders** handle volume rendering

## 📊 Real-time Data Visualization

The system visualizes:

### Scalar Fields
- Concentration distributions
- Temperature gradients
- Current density
- Electric potential

### Particle Systems
- Ion movement
- Bubble generation
- Flow visualization

### Surface Rendering
- Electrode deposition
- Electrolyte level
- Material properties

## 🎨 Customization

### Adding New Instruments

```typescript
function CustomInstrument({ position }) {
  return (
    <group position={position}>
      <Box args={[1, 1, 1]}>
        <meshStandardMaterial color="#ff0000" />
      </Box>
      {/* Add your instrument geometry */}
    </group>
  )
}
```

### Custom Color Maps

```typescript
const customColorMap = new Float32Array([
  // R, G, B, A values for gradient
  1.0, 0.0, 0.0, 1.0,  // Red
  1.0, 1.0, 0.0, 1.0,  // Yellow
  0.0, 1.0, 0.0, 1.0,  // Green
])
```

## 🐛 Troubleshooting

### Black Screen
- Check WebGL support in browser
- Try reducing quality setting
- Clear browser cache

### Low FPS
- Reduce quality to "low"
- Close other browser tabs
- Check GPU acceleration is enabled

### Data Not Updating
- Verify API is running
- Check browser console for errors
- Ensure run is in "running" status

## 🚦 Performance Tips

1. **Use Chrome/Edge** for best WebGL2 performance
2. **Enable GPU acceleration** in browser settings
3. **Close unnecessary tabs** to free GPU memory
4. **Adjust quality settings** based on your hardware
5. **Limit particle count** for complex simulations

## 📈 Next Steps

1. **Try Different Scenarios**: Modify voltage, duration, concentration
2. **Explore Instruments**: Click on each to see interactions
3. **Watch Full Simulation**: See deposition layer grow over time
4. **Export Data**: Use API to get simulation results

## 🔗 Related Documentation

- [System Architecture](VISUALIZATION_ARCHITECTURE.md)
- [API Documentation](API_SPEC.yaml)
- [Implementation Guide](IMPLEMENTATION_GUIDE.md)