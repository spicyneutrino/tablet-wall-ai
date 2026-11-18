import { expect, it } from "vitest";
import { fitTransform } from "./layout";
import { fit as fitMeasured, measureWell } from "./stagePanels";
import type { FitResult } from "./stagePanels";

it("operator_stage_fit.test.js", () => {
    class LabelNode {
        attrs = new Map<string, string>();
        style: Record<string, string> = {};
        dataset: Record<string, string> = {};
        textContent = "";
        getScreenCTM() { return { a: 0, b: 0 }; }
        setAttribute(name: string, value: string | number) { this.attrs.set(name, String(value)); }
        getAttribute(name: string) { return this.attrs.get(name) ?? null; }
    }
    const win = { getComputedStyle: (node: { computed: Record<string, string> }) => node.computed };
    const doc = { defaultView: win, body: { dataset: {} as Record<string, string> } };
    const well = { clientWidth: 1000, clientHeight: 600, getClientRects: (): number[] => [1],
        computed: { paddingLeft: "16px", paddingRight: "16px", paddingTop: "8px", paddingBottom: "8px" } };
    const parent = { computed: { rowGap: "8px" } };
    const tally = { getBoundingClientRect: () => ({ height: 28 }) };
    const field = { parentElement: parent, style: {} as { inlineSize: string },
        computed: { borderLeftWidth: "1px", borderRightWidth: "1px", borderTopWidth: "1px", borderBottomWidth: "1px" } };
    let dragging = false, rotation = 0;
    const label = new LabelNode();
    label.dataset = { width: "667", height: "354", x: "0", y: "0", label: "Screen 1" };
    const svg = { classList: { contains: () => dragging }, ownerDocument: doc,
        viewBox: { baseVal: { width: 720, height: 370 } }, style: {} as { inlineSize: string }, closest: () => field,
        querySelectorAll: (selector: string) => selector === ".operator-slot-label" ? [label] : [] };
    label.getScreenCTM = () => {
        const scale = parseFloat(svg.style.inlineSize) / 720 * 0.35;
        return { a: scale * Math.cos(rotation), b: scale * Math.sin(rotation) };
    };
    const fit = (): FitResult | null => {
        if (!svg.viewBox.baseVal.width) return null;
        const available = measureWell(svg as unknown as SVGSVGElement,
            { well: well as unknown as HTMLElement, field: field as unknown as HTMLElement, tally: tally as unknown as HTMLElement });
        return available ? fitMeasured(svg as unknown as SVGSVGElement, available, { field: field as unknown as HTMLElement }) : null;
    };
    let result = fit();
    expect(result!.width).toBe(966);
    expect(parseFloat(field.style.inlineSize)).toBe(968);
    expect(result!.width / result!.height).toBe(720 / 370);
    const dragSize = { ...svg.style };
    dragging = true;
    expect(fit()).toBe(null);
    expect(svg.style).toEqual(dragSize);
    dragging = false;
    expect(Number(label.getAttribute("font-size")) * Math.hypot(label.getScreenCTM().a, label.getScreenCTM().b)).toBe(16);
    well.clientHeight = 300;
    result = fit();
    expect(result!.height).toBe(246);
    expect(result!.width).toBe(246 * 720 / 370);
    const stable = { ...result! };
    for (const mode of ["content", "arrange", "test"]) {
        doc.body.dataset.mode = mode;
        expect(fit()).toEqual(stable);
    }
    rotation = Math.PI / 3;
    fit();
    expect(Math.abs(Number(label.getAttribute("font-size")) * Math.hypot(label.getScreenCTM().a, label.getScreenCTM().b) - 16) < 1e-10).toBeTruthy();
    well.clientWidth = 170;
    label.dataset.label = "Tablet 2";
    fit();
    expect(label.textContent).toBe("2");
    well.clientWidth = 1000;
    const measured = fitMeasured(svg as unknown as SVGSVGElement, { width: 640, height: 300 }, { field: field as unknown as HTMLElement });
    expect(measured!.height).toBe(300);
    expect(measured!.width).toBe(300 * (720 / 370));
    well.getClientRects = () => [];
    expect(fit()).toBe(null);

    const cover = fitTransform({ kind: "logical", width: 200, height: 200 }, { intrinsicWidth: 1600, intrinsicHeight: 1000, fit: "cover" })!;
    expect(cover.cropX, "1600x1000 on a 200x200 wall crops 37.5% of source width").toBe(0.375);
    expect(cover.cropY, "the fitted source height is fully visible").toBe(0);
    const contain = fitTransform({ kind: "logical", width: 200, height: 200 }, { intrinsicWidth: 1600, intrinsicHeight: 1000, fit: "contain" })!;
    expect(1 - contain.width / 200, "Fit leaves no wall width uncovered").toBe(0);
    expect(1 - contain.height / 200, "Fit leaves 37.5% of wall height uncovered").toBe(0.375);
    const aspects: Record<string, [number, number]> = { wide: [1600, 1000], tall: [1000, 1600], square: [1000, 1000] };
    const walls: Record<string, [number, number]> = { wide: [200, 100], tall: [100, 200], square: [200, 200] };
    for (const [sourceName, [sourceWidth, sourceHeight]] of Object.entries(aspects)) {
        for (const [wallName, [wallWidth, wallHeight]] of Object.entries(walls)) {
            for (const fitMode of ["cover", "contain"]) {
                const transform = fitTransform({ kind: "logical", width: wallWidth, height: wallHeight },
                    { intrinsicWidth: sourceWidth, intrinsicHeight: sourceHeight, fit: fitMode });
                expect(transform, sourceName + " source in a " + wallName + " wall with " + fitMode).toBeTruthy();
                const cropX = transform!.cropX, cropY = transform!.cropY;
                const uncoveredX = 1 - transform!.width / wallWidth, uncoveredY = 1 - transform!.height / wallHeight;
                if (fitMode === "cover") {
                    expect(cropX >= 0 && cropY >= 0 && (cropX === 0 || cropY === 0),
                        "Fill crops at most one source axis: " + sourceName + "/" + wallName).toBeTruthy();
                } else {
                    expect(uncoveredX >= 0 && uncoveredY >= 0 && (uncoveredX === 0 || uncoveredY === 0),
                        "Fit leaves bands on at most one wall axis: " + sourceName + "/" + wallName).toBeTruthy();
                }
            }
        }
    }
    for (const invalid of [undefined, null, 0, -1, NaN, Infinity, "1600", true] as unknown[]) {
        expect(fitTransform({ kind: "logical", width: 200, height: 200 },
            { intrinsicWidth: invalid, intrinsicHeight: 1000, fit: "cover" }),
        "missing or invalid source dimensions never produce a zero estimate").toBe(null);
        expect(fitTransform({ kind: "physical", bounds: { x: 0, y: 0, width: invalid as number, height: 200 } },
            { intrinsicWidth: 1600, intrinsicHeight: 1000, fit: "cover" }),
        "missing or invalid wall bounds never produce a zero estimate").toBe(null);
    }
});
