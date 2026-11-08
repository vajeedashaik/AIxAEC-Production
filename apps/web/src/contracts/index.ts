// Friendly names over the generated contract types (frozen; see phases/shared/CONTRACTS.md).
// "Output" types are what the API returns (every field present). "Input" types are what you may send.
import type * as G from "./generated";

export type {
  Artifact,
  BBox,
  CalibrationSource,
  Candidate,
  ChangeSet,
  CommandRequest,
  CommandResponse,
  Direction,
  Distance,
  EditLogEntry,
  ErrorBody,
  ErrorCode,
  ErrorEnvelope,
  FloorPlan,
  History,
  Insights,
  Job,
  Me,
  MetricInsights,
  ModelEnvelope,
  ModelSummary,
  Point,
  Project,
  ProjectCreate,
  ProjectPage,
  ProjectUpdate,
  ResizeMode,
  RoomRef,
  RoomType,
  Source,
  StageReport,
  VersionInfo,
} from "./generated";

// Building Model (as returned by the API)
export type FloorPlanModel = G.FloorPlanModelOutput;
export type CoordinateSystem = G.CoordinateSystemOutput;
export type Wall = G.WallOutput;
export type Door = G.DoorOutput;
export type Window = G.WindowOutput;
export type Column = G.ColumnOutput;
export type Stair = G.StairOutput;
export type Furniture = G.FurnitureOutput;
export type Dimension = G.DimensionOutput;
export type Room = G.RoomOutput;

// Commands: `Command` is a resolved command as returned; `CommandInput` is what a client may send.
export type Command = NonNullable<G.CommandResponse["command"]>;
export type CommandInput = G.EngineCommand;
export type Analysis = G.Analysis;
export type CostRates = G.CostRatesOutput;
export type CostRatesInput = G.CostRatesInput;
export type ComplianceCheck = G.ComplianceCheck;
export type ComplianceReport = G.ComplianceReport;
export type CostEstimate = G.CostEstimate;
export type Takeoff = G.Takeoff;
export type BoqItem = G.BoqItem;
export type InteriorPlan = G.InteriorPlan;
export type FurniturePlacement = G.FurniturePlacement;
export type StructuralReport = G.StructuralReport;
export type Answer = G.Answer;
export type LayoutSuggestions = G.LayoutSuggestions;
export type Operation = Command["operation"];
export type MoveWall = G.MoveWallOutput;
export type AddWall = G.AddWallOutput;
export type DeleteWall = G.DeleteWallOutput;
export type ResizeRoom = G.ResizeRoomOutput;
export type AddDoor = G.AddDoorOutput;
export type AddWindow = G.AddWindowOutput;
export type DeleteDoor = G.DeleteDoorOutput;
export type DeleteWindow = G.DeleteWindowOutput;
export type RenameRoom = G.RenameRoomOutput;
export type SetScale = G.SetScaleOutput;

export type JobStatus = G.Job["status"];
export type StageName = G.StageReport["name"];
export type CommandStatus = G.CommandResponse["status"];
export type RejectStage = NonNullable<G.CommandResponse["stage"]>;
export type ElementKind = G.Candidate["kind"];
export type ArtifactKind = G.Artifact["kind"];
export type Page<T> = { items: T[]; total: number; limit: number; offset: number };

export const OPERATIONS = [
  "MOVE_WALL",
  "ADD_WALL",
  "DELETE_WALL",
  "RESIZE_ROOM",
  "ADD_DOOR",
  "ADD_WINDOW",
  "DELETE_DOOR",
  "DELETE_WINDOW",
  "RENAME_ROOM",
  "SET_SCALE",
] as const satisfies readonly Operation[];

export const STAGE_NAMES = [
  "preprocess",
  "wall_detection",
  "ocr",
  "object_detection",
  "room_detection",
  "calibration",
  "semantic_assembly",
  "artifacts",
] as const satisfies readonly StageName[];

export const ROOM_TYPES = [
  "UNKNOWN",
  "BEDROOM",
  "MASTER_BEDROOM",
  "BATHROOM",
  "KITCHEN",
  "LIVING_ROOM",
  "DINING_ROOM",
  "HALLWAY",
  "CLOSET",
  "GARAGE",
  "OFFICE",
  "LAUNDRY",
  "BALCONY",
  "STORAGE",
  "STAIRWELL",
  "UTILITY",
  "OTHER",
] as const satisfies readonly G.RoomType[];

/** CSS variable for a room fill, e.g. LIVING_ROOM -> var(--canvas-room-living-room). */
export const roomFillVar = (t: G.RoomType) => `var(--canvas-room-${t.toLowerCase().replace(/_/g, "-")})`;
