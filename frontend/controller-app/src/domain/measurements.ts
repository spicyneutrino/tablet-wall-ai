import type { Viewport } from './calibration';

export type Field = { id?: string; value: string };
export type Fields = Record<string, Field>;
export type Num = (value: string) => number | null;
export type MarkInvalid = (input: Field, invalid: boolean) => void;
export type ValidationErrorCtor = new (message: string) => Error;

type MeasurementFields = {
    profileActiveWidth: Field;
    profileActiveHeight: Field;
    profileBezelLeft: Field;
    profileBezelTop: Field;
    profileBezelRight: Field;
    profileBezelBottom: Field;
    profilePixelWidth: Field;
    profilePixelHeight: Field;
    profileLabel: Field;
    profileProvenance: Field;
    calProfileRevision: Field;
    calViewportWidth: Field;
    calViewportHeight: Field;
    calDpr: Field;
    calOrientation: Field;
    calMode: Field;
    calQuarterTurn: Field;
    calAnchorEdge: Field;
    calOffsetX: Field;
    calOffsetY: Field;
    calMmCssX: Field;
    calMmCssY: Field;
    calUncertainty: Field;
    calMethod: Field;
};

export type ProfileBody = {
    active_width_mm: number;
    active_height_mm: number;
    bezels: { left: number; top: number; right: number; bottom: number };
    panel_pixels: { width: number; height: number } | null;
    label: string;
    provenance: string;
};

export type CalibrationBody = {
    profile_revision: number;
    viewport_width: number;
    viewport_height: number;
    dpr: number;
    orientation: number;
    mode: string;
    quarter_turn: number;
    panel_offset_mm: number[];
    mm_per_css: number[];
    anchor_edge: string;
    uncertainty_mm: number;
    viewport_guard?: boolean;
    method: string;
};

type TextNode = { textContent: string | null };

function setTextIfChanged(node: TextNode | null | undefined, text: string): void {
    if (node && node.textContent !== text) node.textContent = text;
}

export function liveViewportText(viewport: Viewport | null): string {
    return viewport
        ? "Selected tablet: " + viewport.width + " × " + viewport.height + " CSS px · DPR " + viewport.dpr + " · " + viewport.orientation + "° · " + viewport.mode
        : "Waiting for the selected tablet’s online viewport at 100% zoom. Advanced manual entry is available.";
}

export function updateLiveViewport(node: TextNode | null | undefined, viewport: Viewport | null): void {
    setTextIfChanged(node, liveViewportText(viewport));
}

export type CreatePayloadsOptions = {
    fields: Fields;
    num: Num;
    ValidationError?: ValidationErrorCtor;
    markInvalid?: MarkInvalid;
};

export function createPayloads({ fields, num, ValidationError = Error, markInvalid = () => {} }: CreatePayloadsOptions) {
    const el = fields as unknown as MeasurementFields;

    function requirePositive(label: string, input: Field): number {
        const value = num(input.value);
        if (value === null || value <= 0) {
            markInvalid(input, true);
            throw new ValidationError(label + " must be a positive number.");
        }
        markInvalid(input, false);
        return value;
    }

    function requireNonNegative(label: string, input: Field): number {
        const value = num(input.value);
        if (value === null || value < 0) {
            markInvalid(input, true);
            throw new ValidationError(label + " must be a non-negative number.");
        }
        markInvalid(input, false);
        return value;
    }

    function requireFinite(label: string, input: Field): number {
        const value = num(input.value);
        if (value === null) {
            markInvalid(input, true);
            throw new ValidationError(label + " must be a number.");
        }
        markInvalid(input, false);
        return value;
    }

    function requireInteger(label: string, input: Field, minimum: number): number {
        const value = num(input.value);
        if (value === null || !Number.isInteger(value) || value < minimum) {
            markInvalid(input, true);
            throw new ValidationError(label + " must be an integer of at least " + minimum + ".");
        }
        markInvalid(input, false);
        return value;
    }

    function requireText(label: string, input: Field, minimum: number, maximum: number): string {
        const value = input.value.trim();
        if (value.length < minimum || value.length > maximum) {
            markInvalid(input, true);
            throw new ValidationError(label + " must be " + minimum + " to " + maximum + " characters.");
        }
        markInvalid(input, false);
        return value;
    }

    function buildProfileBody(): ProfileBody {
        const panelWidthRaw = el.profilePixelWidth.value.trim();
        const panelHeightRaw = el.profilePixelHeight.value.trim();
        let panelPixels = null;
        if (panelWidthRaw || panelHeightRaw) {
            const width = requirePositive("Panel pixel width", el.profilePixelWidth);
            const height = requirePositive("Panel pixel height", el.profilePixelHeight);
            if (!Number.isInteger(width) || !Number.isInteger(height)) {
                markInvalid(el.profilePixelWidth, true);
                markInvalid(el.profilePixelHeight, true);
                throw new ValidationError("Panel pixel dimensions must be whole numbers.");
            }
            panelPixels = { width: width, height: height };
        }
        return {
            active_width_mm: requirePositive("Active width", el.profileActiveWidth),
            active_height_mm: requirePositive("Active height", el.profileActiveHeight),
            bezels: {
                left: requireNonNegative("Left bezel", el.profileBezelLeft),
                top: requireNonNegative("Top bezel", el.profileBezelTop),
                right: requireNonNegative("Right bezel", el.profileBezelRight),
                bottom: requireNonNegative("Bottom bezel", el.profileBezelBottom)
            },
            panel_pixels: panelPixels,
            label: requireText("Label", el.profileLabel, 1, 80),
            provenance: requireText("Provenance", el.profileProvenance, 1, 40)
        };
    }

    function buildCalibrationBody(): CalibrationBody {
        if (!el.calOrientation.value || !["tab", "fullscreen", "standalone"].includes(el.calMode.value)) {
            throw new ValidationError("Choose the tablet orientation and mode.");
        }
        const orientation = Number(el.calOrientation.value);
        if ([0, 90, 180, 270].indexOf(orientation) === -1) {
            throw new ValidationError("Orientation must be 0, 90, 180 or 270 degrees.");
        }
        const quarter = Number(el.calQuarterTurn.value);
        if ([0, 1, 2, 3].indexOf(quarter) === -1) {
            throw new ValidationError("Quarter turn must be 0, 1, 2 or 3.");
        }
        const anchor = el.calAnchorEdge.value;
        if (["top-left", "top-right", "bottom-left", "bottom-right"].indexOf(anchor) === -1) {
            throw new ValidationError("Anchor edge is not supported.");
        }
        return {
            profile_revision: requireInteger("Profile revision", el.calProfileRevision, 1),
            viewport_width: requirePositive("Viewport width", el.calViewportWidth),
            viewport_height: requirePositive("Viewport height", el.calViewportHeight),
            dpr: requirePositive("Device pixel ratio", el.calDpr),
            orientation: orientation,
            mode: el.calMode.value,
            quarter_turn: quarter,
            panel_offset_mm: [
                requireFinite("Panel offset X", el.calOffsetX),
                requireFinite("Panel offset Y", el.calOffsetY)
            ],
            mm_per_css: [
                requirePositive("mm per CSS pixel X", el.calMmCssX),
                requirePositive("mm per CSS pixel Y", el.calMmCssY)
            ],
            anchor_edge: anchor,
            uncertainty_mm: requireNonNegative("Uncertainty", el.calUncertainty),
            ...(el.calMethod.value.trim() === "ruler-measured" ? { viewport_guard: true } : {}),
            method: requireText("Method", el.calMethod, 1, 80)
        };
    }

    return { buildProfileBody, buildCalibrationBody, requireInteger, requireNonNegative };
}
