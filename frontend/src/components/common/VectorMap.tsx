import { useEffect, useRef, type CSSProperties, type RefObject } from "react";
import jsVectorMap from "jsvectormap";

if (typeof window !== "undefined") {
  window.jsVectorMap = jsVectorMap;
}

import "jsvectormap/dist/maps/world.js";

type FlatVectorMapMarkerStyle = jsVectorMap.StyleAttributes & {
  borderWidth?: number | string;
  borderColor?: string;
  initial?: never;
  hover?: never;
  selected?: never;
  selectedHover?: never;
};

type VectorMapMarkerStyle = jsVectorMap.ElementStyle | FlatVectorMapMarkerStyle;

type VectorMapMapData = jsVectorMap.MapData & { name: string };

export type VectorMapMarker = {
  name?: string;
  coords?: jsVectorMap.Coords;
  latLng?: jsVectorMap.Coords;
  style?: VectorMapMarkerStyle;
  offsets?: jsVectorMap.Offset;
  [key: string]: unknown;
};

export type VectorMapProps = {
  map?: string | VectorMapMapData;
  containerStyle?: CSSProperties;
  containerClassName?: string;
  backgroundColor?: string;
  zoomOnScroll?: boolean;
  zoomOnScrollSpeed?: number;
  zoomMax?: number;
  zoomMin?: number;
  zoomAnimate?: boolean;
  zoomStep?: number;
  zoomButtons?: boolean;
  markers?: VectorMapMarker[];
  markerStyle?: jsVectorMap.ElementStyle;
  markersSelectable?: boolean;
  markersSelectableOne?: boolean;
  selectedMarkers?: Array<string | number>;
  regionStyle?: jsVectorMap.ElementStyle;
  regionLabelStyle?: jsVectorMap.ElementStyle;
  regionsSelectable?: boolean;
  regionsSelectableOne?: boolean;
  selectedRegions?: string[];
  labels?: jsVectorMap.Labels;
  lines?: jsVectorMap.LineConfig[];
  lineStyle?: jsVectorMap.LineStyle;
  series?: jsVectorMap.SeriesOptions;
  visualizeData?: jsVectorMap.VisualizeDataOptions;
  focusOn?: jsVectorMap.FocusConfig;
  onLoaded?: (map: jsVectorMap) => void;
  onRegionClick?: (event: MouseEvent, code: string) => void;
  onMarkerClick?: (event: MouseEvent, index: string) => void;
  onRegionSelected?: (
    code: string,
    isSelected: boolean,
    selectedRegions: string[],
  ) => void;
  onMarkerSelected?: (
    index: string,
    isSelected: boolean,
    selectedMarkers: string[],
  ) => void;
  onRegionTipShow?: (
    event: MouseEvent,
    tooltip: jsVectorMap.Tooltip,
    code: string,
  ) => void;
  onMarkerTipShow?: (
    event: MouseEvent,
    tooltip: jsVectorMap.Tooltip,
    index: number,
  ) => void;
  onRegionTooltipShow?: (
    event: MouseEvent,
    tooltip: jsVectorMap.Tooltip,
    code: string,
  ) => void;
  onMarkerTooltipShow?: (
    event: MouseEvent,
    tooltip: jsVectorMap.Tooltip,
    index: string,
  ) => void;
  onViewportChange?: (scale: number, transX: number, transY: number) => void;
  onDestroyed?: () => void;
  mapRef?: RefObject<VectorMapInstance | null>;
  style?: CSSProperties;
  className?: string;
};

function isElementStyle(
  style: VectorMapMarkerStyle,
): boolean {
  return (
    "initial" in style ||
    "hover" in style ||
    "selected" in style ||
    "selectedHover" in style
  );
}

function normalizeMarkerStyle(
  style: VectorMapMarkerStyle | undefined,
): jsVectorMap.ElementStyle | undefined {
  if (!style) return undefined;
  if (isElementStyle(style)) return style;

  const { borderWidth, borderColor, ...initial } =
    style as FlatVectorMapMarkerStyle;
  return {
    initial: {
      ...initial,
      ...(borderWidth !== undefined ? { strokeWidth: borderWidth } : {}),
      ...(borderColor !== undefined ? { stroke: borderColor } : {}),
    },
  };
}

type VectorMapScale = (
  scale: number,
  anchorX?: number,
  anchorY?: number,
  isCentered?: boolean,
  animate?: boolean,
) => void;

type VectorMapZoomHelpers = {
  setScale: VectorMapScale;
  width: number;
  height: number;
};

type VectorMapInstance = InstanceType<typeof jsVectorMap> & VectorMapZoomHelpers;

type InternalVectorMapInstance = InstanceType<typeof jsVectorMap> & {
  _setScale: VectorMapScale;
  _width?: number;
  _height?: number;
  setScale?: VectorMapScale;
  width?: number;
  height?: number;
};

function addZoomCompatibility(
  map: InstanceType<typeof jsVectorMap>,
  node: HTMLElement,
): VectorMapInstance {
  const internalMap = map as InternalVectorMapInstance;

  if (typeof internalMap.setScale !== "function") {
    internalMap.setScale = (scale, anchorX, anchorY, isCentered, animate) => {
      internalMap._setScale(scale, anchorX, anchorY, isCentered, animate);
    };
  }

  if (!Object.prototype.hasOwnProperty.call(internalMap, "width")) {
    Object.defineProperty(internalMap, "width", {
      get: () => internalMap._width ?? node.clientWidth ?? 0,
      configurable: true,
    });
  }

  if (!Object.prototype.hasOwnProperty.call(internalMap, "height")) {
    Object.defineProperty(internalMap, "height", {
      get: () => internalMap._height ?? node.clientHeight ?? 0,
      configurable: true,
    });
  }

  return internalMap as VectorMapInstance;
}

export function VectorMap({
  map = "world",
  containerStyle,
  containerClassName,
  backgroundColor = "transparent",
  zoomOnScroll = false,
  zoomOnScrollSpeed,
  zoomMax = 12,
  zoomMin = 1,
  zoomAnimate = true,
  zoomStep = 1.5,
  zoomButtons = false,
  markers,
  markerStyle,
  markersSelectable,
  markersSelectableOne,
  selectedMarkers,
  regionStyle,
  regionLabelStyle,
  regionsSelectable,
  regionsSelectableOne,
  selectedRegions,
  labels,
  lines,
  lineStyle,
  series,
  visualizeData,
  focusOn,
  onLoaded,
  onRegionClick,
  onMarkerClick,
  onRegionSelected,
  onMarkerSelected,
  onRegionTipShow,
  onMarkerTipShow,
  onRegionTooltipShow,
  onMarkerTooltipShow,
  onViewportChange,
  onDestroyed,
  mapRef,
  style,
  className,
}: VectorMapProps) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    node.innerHTML = "";

    let mapName = "world";
    if (typeof map === "string") {
      if (map === "world" || map === "worldMill" || map === "worldMerc") {
        mapName = "world";
      } else if (map === "usAea" || map === "us_aea" || map === "us_aea_en") {
        mapName = "us_aea_en";
      } else {
        mapName = map;
      }
    } else if (map && typeof map === "object") {
      if (map.name) {
        mapName = map.name;
        jsVectorMap.addMap(mapName, map);
      }
    }
    const normalizedMarkers: jsVectorMap.MarkerConfig[] | undefined =
      markers?.map((marker) => ({
        ...marker,
        coords: marker.coords ?? marker.latLng ?? [0, 0],
        style: normalizeMarkerStyle(marker.style),
      }));

    let mapInstance: VectorMapInstance | null = null;

    try {
      const options: jsVectorMap.MapOptions = {
        selector: node,
        map: mapName,
        backgroundColor,
        draggable: true,
        zoomButtons,
        zoomOnScroll,
        ...(zoomOnScrollSpeed !== undefined ? { zoomOnScrollSpeed } : {}),
        zoomMax,
        zoomMin,
        zoomAnimate,
        zoomStep,
        ...(normalizedMarkers !== undefined
          ? { markers: normalizedMarkers }
          : {}),
        ...(markerStyle ? { markerStyle } : {}),
        markersSelectable:
          markersSelectable ?? Boolean(selectedMarkers && selectedMarkers.length > 0),
        ...(markersSelectableOne !== undefined ? { markersSelectableOne } : {}),
        ...(selectedMarkers ? { selectedMarkers } : {}),
        ...(regionStyle ? { regionStyle } : {}),
        ...(regionLabelStyle ? { regionLabelStyle } : {}),
        regionsSelectable:
          regionsSelectable ?? Boolean(selectedRegions && selectedRegions.length > 0),
        ...(regionsSelectableOne !== undefined ? { regionsSelectableOne } : {}),
        ...(selectedRegions ? { selectedRegions } : {}),
        ...(labels ? { labels } : {}),
        ...(lines ? { lines } : {}),
        ...(lineStyle ? { lineStyle } : {}),
        ...(series ? { series } : {}),
        ...(visualizeData ? { visualizeData } : {}),
        ...(focusOn ? { focusOn } : {}),
        ...(onLoaded ? { onLoaded } : {}),
        ...(onRegionClick ? { onRegionClick } : {}),
        ...(onMarkerClick ? { onMarkerClick } : {}),
        ...(onRegionSelected ? { onRegionSelected } : {}),
        ...(onMarkerSelected ? { onMarkerSelected } : {}),
        ...(onRegionTooltipShow
          ? { onRegionTooltipShow }
          : onRegionTipShow
            ? {
                onRegionTooltipShow: (
                  event: MouseEvent,
                  tooltip: jsVectorMap.Tooltip,
                  code: string,
                ) => onRegionTipShow(event, tooltip, code),
              }
            : {}),
        ...(onMarkerTooltipShow
          ? { onMarkerTooltipShow }
          : onMarkerTipShow
            ? {
                onMarkerTooltipShow: (
                  event: MouseEvent,
                  tooltip: jsVectorMap.Tooltip,
                  index: string,
                ) => onMarkerTipShow(event, tooltip, Number(index)),
              }
            : {}),
        ...(onViewportChange ? { onViewportChange } : {}),
        ...(onDestroyed ? { onDestroyed } : {}),
      };
      mapInstance = addZoomCompatibility(new jsVectorMap(options), node);
      if (mapRef) {
        mapRef.current = mapInstance;
      }
    } catch (err) {
      console.error("Failed to initialize jsVectorMap:", err);
    }

    return () => {
      if (mapRef?.current === mapInstance) {
        mapRef.current = null;
      }
      mapInstance?.destroy();
      node.innerHTML = "";
    };
  }, [
    map,
    backgroundColor,
    zoomOnScroll,
    zoomOnScrollSpeed,
    zoomMax,
    zoomMin,
    zoomAnimate,
    zoomStep,
    zoomButtons,
    markers,
    markerStyle,
    markersSelectable,
    markersSelectableOne,
    selectedMarkers,
    regionStyle,
    regionLabelStyle,
    regionsSelectable,
    regionsSelectableOne,
    selectedRegions,
    labels,
    lines,
    lineStyle,
    series,
    visualizeData,
    focusOn,
    onLoaded,
    onRegionClick,
    onMarkerClick,
    onRegionSelected,
    onMarkerSelected,
    onRegionTipShow,
    onMarkerTipShow,
    onRegionTooltipShow,
    onMarkerTooltipShow,
    onViewportChange,
    onDestroyed,
    mapRef,
  ]);

  const combinedClassName = [containerClassName, className]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      ref={ref}
      className={combinedClassName || undefined}
      style={{ width: "100%", height: "100%", ...containerStyle, ...style }}
    />
  );
}

export default VectorMap;
