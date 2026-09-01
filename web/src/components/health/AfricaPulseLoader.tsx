import "./AfricaPulseLoader.css";

/**
 * AfricaPulseLoader
 *
 * A resizable loading indicator: the African continent (plus Madagascar)
 * rendered as a field of dots, with a travelling impulse rippling outward
 * from the centre of the point cloud, brightening and scaling each dot as
 * it passes before it settles back to rest. Meant to read like a signal
 * propagating across the map or a slow, clinical heartbeat - not a spinner.
 *
 * Purely presentational: no data fetching, no app imports. Everything is
 * driven off the SVG viewBox, so it scales to whatever box it is given.
 *
 * Honours prefers-reduced-motion by falling back to a gentle, synchronised
 * opacity pulse (see AfricaPulseLoader.css) instead of the travelling wave.
 */

interface AfricaPulseLoaderProps {
  /** CSS length for both width and height, e.g. "3rem", "64px", "100%". */
  size?: string;
  /** Extra classes applied to the outer wrapper. */
  className?: string;
  /** Accessible name for the status role. */
  label?: string;
}

// Point cloud filling a simplified Africa + Madagascar silhouette.
// Coordinates live in an abstract 0-300ish unit space (see VIEW_BOX below),
// built from the approximate positions of coastal landmarks, not traced
// from an image. Plain [x, y] tuples so the shape can be hand-edited later:
// add, remove, or nudge a pair to reshape the coastline. Points after the
// marker below form Madagascar.
const DOTS: ReadonlyArray<readonly [number, number]> = [
  // --- mainland ---
  [86.2, 6.7], [110.2, 5.1], [61.2, 17], [74.1, 17.3], [86, 17.6], [95.9, 16.3], [109.5, 17.3], [121.6, 16.7], [48.4, 29.8], [58.4, 30.8],
  [74.4, 28.8], [85.2, 31.4], [98, 29], [109.2, 30.8], [124.2, 30.3], [135.3, 29.9], [149.1, 31.5], [161.7, 30.9], [172.9, 31.8], [185.7, 28.7],
  [196.5, 31.2], [34.8, 42.4], [45.6, 42.9], [61.3, 42.1], [73.8, 43], [83.5, 42.7], [98.3, 43], [109.9, 44.1], [122.7, 40.4], [136.6, 41.3],
  [149.1, 43.4], [159.3, 40.5], [171.3, 42.9], [184.5, 42.7], [195.6, 43.4], [208.2, 43], [35.1, 56.7], [48.1, 55.9], [61.8, 53.7], [71.2, 54.6],
  [85, 53.5], [98.7, 55.7], [112, 55.4], [121.7, 53.4], [133.9, 55.9], [148.6, 53.4], [160, 56], [172.8, 55.4], [183.1, 55.5], [198.3, 53.8],
  [209.9, 56.5], [21.6, 65.7], [33, 67.2], [45.7, 67.7], [61.1, 68.1], [72.3, 67.2], [84.7, 66.9], [98.2, 67.9], [111.2, 65.9], [121.7, 67.4],
  [136.1, 66.5], [146.9, 66.7], [160, 67.3], [171.6, 67.3], [184.9, 66.2], [196.6, 69.1], [209.1, 65.7], [223.4, 67.9], [21.2, 79.1], [35.1, 81.3],
  [48.8, 80.1], [61.9, 79.9], [72, 79.4], [83.3, 81.1], [97.6, 80.8], [109.7, 79.6], [121.9, 79.3], [136, 78.8], [149.5, 78.7], [161.5, 79.8],
  [172.9, 78.9], [186.9, 78], [196.8, 81.1], [210.6, 80.9], [223.8, 80.4], [234.2, 78.1], [11.3, 93.6], [21.4, 92], [33.5, 93.3], [49.2, 92.2],
  [61.9, 90.5], [71, 91.6], [85.9, 92.8], [98.4, 92.7], [108.8, 90.7], [122.6, 92.3], [133.7, 93.9], [148.6, 93.9], [158.6, 93.4], [173.2, 91.7],
  [186.1, 92.8], [198, 91.4], [208.6, 91.5], [222.1, 91.9], [236.7, 90.3], [248, 92.1], [24.2, 104.2], [36.5, 105.5], [47.8, 104], [61.3, 103.7],
  [71, 105.5], [84.4, 106.6], [95.5, 103.9], [109.4, 103.9], [123.9, 105.8], [135.9, 106.6], [147.2, 104.3], [159, 105], [172.2, 104.6], [186.4, 104.1],
  [195.7, 105.5], [210.3, 103], [220.8, 105.3], [235.7, 106.6], [249.3, 105.6], [284.6, 106.1], [33.4, 115.4], [49.3, 116.8], [58.9, 116.5], [73.3, 118.2],
  [84.6, 118.5], [98.4, 116.7], [109.5, 116.8], [122.2, 117.3], [136.9, 117.4], [149.1, 116.7], [160.2, 118.8], [172.9, 115.5], [184.7, 117.1], [196.5, 115.9],
  [211.2, 115.5], [223.3, 118.1], [235.2, 118.6], [248.9, 118.2], [260.8, 118], [270.8, 118.1], [60.6, 130.1], [73, 129.5], [108.6, 130.4], [121.1, 128],
  [135.2, 128], [149.3, 127.9], [161.6, 131.5], [172.8, 131], [186.1, 129.1], [196.1, 128.2], [211.3, 128.8], [224.3, 131.7], [233.7, 129.2], [249.3, 128.1],
  [261, 127.8], [123.6, 144.1], [135.2, 141.8], [147.4, 140.6], [158.2, 144], [171.4, 142.8], [184.1, 143], [196.9, 142.4], [211.2, 141.2], [224.2, 143.1],
  [235.4, 142.1], [248.1, 142.6], [261.6, 143.2], [124, 154.5], [134.7, 154.6], [149.2, 156.3], [161.8, 153.5], [170.9, 154.8], [186.7, 153.4], [195.9, 154.6],
  [209.1, 155.1], [223, 154.9], [236.2, 154], [246.4, 155.4], [134.2, 169], [145.6, 166.1], [161.1, 165.8], [172.1, 167.3], [184.5, 168.1], [197.8, 167.9],
  [208.7, 165.3], [224.4, 169.1], [235.6, 168.4], [136, 177.9], [145.9, 180.5], [160.4, 178.8], [172.9, 178.7], [183.2, 180.6], [199.5, 181.7], [209, 179.5],
  [224, 178.8], [234.3, 180.8], [135.5, 191.2], [145.6, 193.1], [159.6, 192.8], [174.1, 192], [185.8, 192.8], [198.9, 190.4], [210.3, 191.2], [220.9, 192.8],
  [149.4, 204.3], [161.3, 203.3], [172.9, 206], [184.3, 205.8], [195.9, 206.7], [210.3, 203.2], [223.6, 204.9], [147.9, 215.7], [158.5, 216.4], [171.8, 219.2],
  [184, 216.2], [198.8, 217.1], [208.2, 216.5], [223.1, 216.8], [149.4, 229.2], [160.8, 227.9], [172.2, 228.8], [184.4, 230.4], [196.4, 228.9], [212, 229.9],
  [149.4, 240.8], [159.6, 243.3], [171.4, 240.4], [185, 243.1], [197.1, 242.9], [209.1, 242.8], [147.7, 253.4], [160.3, 253.5], [172.7, 253.7], [185.3, 256.2],
  [195.8, 256.7], [209.4, 253.2], [147.3, 267.1], [159.8, 267.7], [171.2, 269], [183.3, 266], [197.1, 265.7], [158.7, 281.4], [171.1, 277.8], [184.8, 279.6],
  // --- madagascar ---
  [277.6, 205.7], [265.9, 211.2], [271.6, 211.3], [277.4, 211.2], [259.4, 218.2], [264.9, 217.5], [270.8, 217.3], [278.1, 217.8], [258.4, 224.6], [265, 223.6],
  [271.8, 223.5], [276.2, 224.4], [259, 229.5], [265.4, 230.6], [270.3, 230.7], [258.3, 235.1], [266.2, 235.3], [271.5, 235.7], [259.6, 242.8], [264.3, 242],
  [270.5, 242.3], [258.7, 248.1], [266.1, 247.2],
];

// Padding around the point cloud's bounding box so the wave's peak scale
// never clips against the viewBox edge.
const VIEW_BOX = "-4 -4 300 300";

const DOT_RADIUS = 2.1;

// One full pulse cycle: a short travelling burst, then a longer rest so it
// reads as a heartbeat rather than a shimmer.
const CYCLE_SECONDS = 3.4;
// How long (in seconds) it takes the wavefront to travel from the centre
// of the point cloud to its furthest dot.
const SPREAD_SECONDS = 1;

// Heal theme (see web/tailwind.config.js): heal.ink.300 for resting dots,
// heal.teal.400 for the pulse peak.
const DOT_REST_COLOR = "#cbd5da";
const DOT_PEAK_COLOR = "#2dd4bf";

// Wave origin: the centroid of the point cloud. Distance from this point
// (normalised against the furthest dot) drives each dot's animation delay,
// so the pulse reads as a ripple expanding outward from the middle of the
// continent - a coherent, single direction of travel.
const CENTROID = DOTS.reduce(
  (acc, [x, y]) => ({ x: acc.x + x / DOTS.length, y: acc.y + y / DOTS.length }),
  { x: 0, y: 0 },
);

const MAX_DISTANCE = Math.max(
  ...DOTS.map(([x, y]) => Math.hypot(x - CENTROID.x, y - CENTROID.y)),
);

export const AfricaPulseLoader: React.FC<AfricaPulseLoaderProps> = ({
  size = "4rem",
  className,
  label = "Loading",
}) => {
  return (
    <div
      role="status"
      aria-label={label}
      className={className}
      style={{ width: size, height: size, lineHeight: 0 }}
    >
      <svg
        viewBox={VIEW_BOX}
        width="100%"
        height="100%"
        aria-hidden="true"
        focusable="false"
        style={
          {
            "--heal-dot-rest": DOT_REST_COLOR,
            "--heal-dot-peak": DOT_PEAK_COLOR,
          } as React.CSSProperties
        }
      >
        {DOTS.map(([x, y], index) => {
          const distance = Math.hypot(x - CENTROID.x, y - CENTROID.y);
          const delay = (distance / MAX_DISTANCE) * SPREAD_SECONDS;
          return (
            <circle
              key={index}
              className="heal-pulse-dot"
              cx={x}
              cy={y}
              r={DOT_RADIUS}
              style={{
                animationDuration: `${CYCLE_SECONDS}s`,
                animationDelay: `${delay.toFixed(3)}s`,
              }}
            />
          );
        })}
      </svg>
    </div>
  );
};

export default AfricaPulseLoader;
