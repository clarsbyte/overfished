import { useGlobeControlsContext, type GlobeControlsState } from "./GlobeControlsContext";

export type { GlobeControlsState };

export function useGlobeControls(): GlobeControlsState {
  const { controls } = useGlobeControlsContext();
  return controls;
}
