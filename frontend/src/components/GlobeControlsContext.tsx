import { createContext, useContext, useState, ReactNode, useCallback } from "react";

export interface GlobeControlsState {
    // ─ Flight-path controls (the new InstancedMesh layer)
    flightCount: number;
    dashSize: number;
    gapSize: number;
    arcMinAltitude: number;
    arcMaxAltitude: number;
    showPaths: boolean;
    showVessels: boolean;
    vesselSize: number;
    animationSpeed: number;
    vesselElevation: number;
    tiltMode: "Perpendicular" | "Tangent";
    // ─ Legacy globe overlays
    showHeatmap: boolean;
    showPoints: boolean;
}

const DEFAULT_STATE: GlobeControlsState = {
    flightCount: 250,
    dashSize: 1.0,
    gapSize: 0.4,
    arcMinAltitude: 2.5,
    arcMaxAltitude: 9,
    showPaths: true,
    showVessels: true,
    vesselSize: 1.6,
    animationSpeed: 0.05,
    vesselElevation: 0.8,
    tiltMode: "Perpendicular",
    showHeatmap: true,
    showPoints: false,
};

interface GlobeControlsContextType {
    controls: GlobeControlsState;
    setControl: <K extends keyof GlobeControlsState>(key: K, value: GlobeControlsState[K]) => void;
    isUpdatingLayers: boolean;
    toggleLayer: (layer: "showPaths" | "showVessels" | "showHeatmap" | "showPoints") => void;
}

const GlobeControlsContext = createContext<GlobeControlsContextType | null>(null);

export function GlobeControlsProvider({ children }: { children: ReactNode }) {
    const [controls, setControls] = useState<GlobeControlsState>(DEFAULT_STATE);
    const [isUpdatingLayers, setIsUpdatingLayers] = useState(false);

    const setControl = useCallback(<K extends keyof GlobeControlsState>(key: K, value: GlobeControlsState[K]) => {
        setControls((prev) => ({ ...prev, [key]: value }));
    }, []);

    const toggleLayer = useCallback((layer: "showPaths" | "showVessels" | "showHeatmap" | "showPoints") => {
        // Show spinner immediately
        setIsUpdatingLayers(true);

        // Yield to the browser so the React UI can paint the spinner, 
        // then apply the actual state change which might trigger a heavy 3D recalculation
        requestAnimationFrame(() => {
            setTimeout(() => {
                setControls((prev) => ({ ...prev, [layer]: !prev[layer] }));

                // Let the 3D process run, then hide the spinner slightly after to ensure a smooth transition
                setTimeout(() => setIsUpdatingLayers(false), 500);
            }, 50);
        });
    }, []);

    return (
        <GlobeControlsContext.Provider value={{ controls, setControl, isUpdatingLayers, toggleLayer }}>
            {children}
        </GlobeControlsContext.Provider>
    );
}

export function useGlobeControlsContext() {
    const ctx = useContext(GlobeControlsContext);
    if (!ctx) throw new Error("useGlobeControlsContext must be used within GlobeControlsProvider");
    return ctx;
}
