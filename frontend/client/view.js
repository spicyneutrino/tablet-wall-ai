/*
 * Version-3 physical geometry for the wall client.
 *
 * Spaces: W wall millimetres (X right, Y down, viewed from the audience),
 * B body millimetres centred on the tablet in its native orientation,
 * P active-panel millimetres with the origin at the panel's top-left,
 * C CSS pixels, D canvas backing pixels, N normalized upright source.
 *
 * Matrices are six-number Canvas arrays [a,b,c,d,e,f] with column vectors,
 * so x' = a*x + c*y + e and y' = b*x + d*y + f. multiply(left, right)
 * applies right first. Positive rotation is clockwise in this Y-down space.
 *
 * bodyGeometry returns { width, height, activeOrigin: [x, y] }; every other
 * result uses the same field names as the server-side geometry module.
 */
(function () {
    "use strict";

    var IDENTITY = [1, 0, 0, 1, 0, 0];

    function fail(message) {
        throw new Error(message);
    }

    function finiteNumber(value, label) {
        if (typeof value !== "number" || !Number.isFinite(value)) {
            fail(label + " must be a finite number");
        }
        return value;
    }

    function positive(value, message) {
        if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
            fail(message);
        }
        return value;
    }

    function nonNegative(value, label) {
        if (typeof value !== "number") fail(label + " must be a number");
        if (!Number.isFinite(value) || value < 0) {
            fail(label + " must be finite and non-negative");
        }
        return value;
    }

    function multiply(left, right) {
        var a = left[0], b = left[1], c = left[2];
        var d = left[3], e = left[4], f = left[5];
        var g = right[0], h = right[1], i = right[2];
        var j = right[3], k = right[4], l = right[5];
        return [
            a * g + c * h,
            b * g + d * h,
            a * i + c * j,
            b * i + d * j,
            a * k + c * l + e,
            b * k + d * l + f
        ];
    }

    function inverse(matrix) {
        var a = matrix[0], b = matrix[1], c = matrix[2];
        var d = matrix[3], e = matrix[4], f = matrix[5];
        var determinant = a * d - b * c;
        if (Math.abs(determinant) < 1e-12) fail("matrix is not invertible");
        return [
            d / determinant,
            -b / determinant,
            -c / determinant,
            a / determinant,
            (c * f - d * e) / determinant,
            (b * e - a * f) / determinant
        ];
    }

    function apply(matrix, point) {
        var a = matrix[0], b = matrix[1], c = matrix[2];
        var d = matrix[3], e = matrix[4], f = matrix[5];
        var x = point[0], y = point[1];
        return [a * x + c * y + e, b * x + d * y + f];
    }

    function translate(tx, ty) {
        finiteNumber(tx, "tx");
        finiteNumber(ty, "ty");
        return [1, 0, 0, 1, tx, ty];
    }

    function scale(sx, sy) {
        finiteNumber(sx, "sx");
        finiteNumber(sy, "sy");
        if (sx === 0 || sy === 0) fail("scale must be non-zero");
        return [sx, 0, 0, sy, 0, 0];
    }

    function rotate(angleDegrees) {
        finiteNumber(angleDegrees, "angle");
        var radians = (angleDegrees * Math.PI) / 180;
        var cosine = Math.cos(radians);
        var sine = Math.sin(radians);
        return [cosine, sine, -sine, cosine, 0, 0];
    }

    function quarterTurn(quarter, viewportWidth, viewportHeight) {
        if (quarter !== 0 && quarter !== 1 && quarter !== 2 && quarter !== 3) {
            fail("quarter_turn must be 0, 1, 2 or 3");
        }
        positive(viewportWidth, "viewport dimensions must be positive");
        positive(viewportHeight, "viewport dimensions must be positive");
        var w = viewportWidth;
        var h = viewportHeight;
        if (quarter === 0) return [1, 0, 0, 1, 0, 0];
        if (quarter === 1) return [0, 1, -1, 0, h, 0];
        if (quarter === 2) return [-1, 0, 0, -1, w, h];
        return [0, -1, 1, 0, 0, w];
    }

    function bodyGeometry(activeWidth, activeHeight, bezels) {
        positive(activeWidth, "active dimensions must be positive");
        positive(activeHeight, "active dimensions must be positive");
        if (!bezels || typeof bezels !== "object") {
            fail("bezels must be an object");
        }
        var left = nonNegative(bezels.left, "left bezel");
        var top = nonNegative(bezels.top, "top bezel");
        var right = nonNegative(bezels.right, "right bezel");
        var bottom = nonNegative(bezels.bottom, "bottom bezel");
        var width = left + activeWidth + right;
        var height = top + activeHeight + bottom;
        return {
            width: width,
            height: height,
            activeOrigin: [-width / 2 + left, -height / 2 + top]
        };
    }

    function fitMatrix(bounds, sourceWidth, sourceHeight, fit) {
        var x = finiteNumber(bounds[0], "bounds x");
        var y = finiteNumber(bounds[1], "bounds y");
        var width = positive(bounds[2], "bounds and source dimensions must be positive");
        var height = positive(bounds[3], "bounds and source dimensions must be positive");
        positive(sourceWidth, "bounds and source dimensions must be positive");
        positive(sourceHeight, "bounds and source dimensions must be positive");
        var factor;
        if (fit === "cover") {
            factor = Math.max(width / sourceWidth, height / sourceHeight);
        } else if (fit === "contain") {
            factor = Math.min(width / sourceWidth, height / sourceHeight);
        } else {
            fail("unsupported fit " + JSON.stringify(fit));
        }
        var drawWidth = factor * sourceWidth;
        var drawHeight = factor * sourceHeight;
        return [
            drawWidth,
            0,
            0,
            drawHeight,
            x + (width - drawWidth) / 2,
            y + (height - drawHeight) / 2
        ];
    }

    function panelToWall(activeOrigin, centerMm, nudgeMm, mountAngle) {
        var body = translate(
            finiteNumber(centerMm[0], "center x") + finiteNumber(nudgeMm[0], "nudge x"),
            finiteNumber(centerMm[1], "center y") + finiteNumber(nudgeMm[1], "nudge y")
        );
        return multiply(
            multiply(
                body,
                rotate(finiteNumber(mountAngle, "mount angle"))
            ),
            translate(
                finiteNumber(activeOrigin[0], "active origin x"),
                finiteNumber(activeOrigin[1], "active origin y")
            )
        );
    }

    function normalizedSourceToPanel(options) {
        var activeWidth = options.active_size[0];
        var activeHeight = options.active_size[1];
        var body = bodyGeometry(activeWidth, activeHeight, options.bezels);
        var panelToWallMatrix = panelToWall(
            body.activeOrigin,
            options.center_mm,
            options.nudge_mm,
            options.mount_angle
        );
        var fitToWall = fitMatrix(
            options.bounds,
            options.source_size[0],
            options.source_size[1],
            options.fit
        );
        return {
            panel_from_source: multiply(inverse(panelToWallMatrix), fitToWall),
            panel_to_wall: panelToWallMatrix,
            body: { width: body.width, height: body.height },
            active: {
                x: body.activeOrigin[0],
                y: body.activeOrigin[1],
                width: activeWidth,
                height: activeHeight
            },
            clip: { x: 0, y: 0, width: activeWidth, height: activeHeight }
        };
    }

    function cssToPanel(options) {
        var mmX = options.mm_per_css[0];
        var mmY = options.mm_per_css[1];
        positive(mmX, "mm_per_css must be positive");
        positive(mmY, "mm_per_css must be positive");
        return multiply(
            translate(options.panel_offset_mm[0], options.panel_offset_mm[1]),
            multiply(
                quarterTurn(
                    options.quarter_turn,
                    options.viewport_width * mmX,
                    options.viewport_height * mmY
                ),
                scale(mmX, mmY)
            )
        );
    }

    function backingScale(backing, rect) {
        positive(rect[0], "render rectangle must be positive");
        positive(rect[1], "render rectangle must be positive");
        return scale(backing[0] / rect[0], backing[1] / rect[1]);
    }

    function canvasTransform(options) {
        var calibration = options.calibration;
        var uCToPanel = cssToPanel({
            viewport_width: calibration.viewport_width,
            viewport_height: calibration.viewport_height,
            quarter_turn: calibration.quarter_turn,
            panel_offset_mm: calibration.panel_offset_mm,
            mm_per_css: calibration.mm_per_css
        });
        var sourceToNormalized = scale(
            1 / options.source_size[0],
            1 / options.source_size[1]
        );
        return multiply(
            backingScale(options.backing, options.rect),
            multiply(
                inverse(uCToPanel),
                multiply(options.panel_from_source, sourceToNormalized)
            )
        );
    }

    function canvasTransformComponents(options) {
        var calibration = options.calibration;
        var uCToPanel = cssToPanel({
            viewport_width: calibration.viewport_width,
            viewport_height: calibration.viewport_height,
            quarter_turn: calibration.quarter_turn,
            panel_offset_mm: calibration.panel_offset_mm,
            mm_per_css: calibration.mm_per_css
        });
        var clip = calibration.clip || {
            x: 0,
            y: 0,
            width: calibration.panel_width || 0,
            height: calibration.panel_height || 0
        };
        var clipMatrix = multiply(
            backingScale(options.backing, options.rect),
            inverse(uCToPanel)
        );
        var corners = [
            apply(clipMatrix, [clip.x, clip.y]),
            apply(clipMatrix, [clip.x + clip.width, clip.y]),
            apply(clipMatrix, [clip.x, clip.y + clip.height]),
            apply(clipMatrix, [clip.x + clip.width, clip.y + clip.height])
        ];
        var xs = [corners[0][0], corners[1][0], corners[2][0], corners[3][0]];
        var ys = [corners[0][1], corners[1][1], corners[2][1], corners[3][1]];
        var minX = Math.min.apply(null, xs);
        var maxX = Math.max.apply(null, xs);
        var minY = Math.min.apply(null, ys);
        var maxY = Math.max.apply(null, ys);
        return {
            matrix: canvasTransform(options),
            clip: {
                x: minX,
                y: minY,
                width: maxX - minX,
                height: maxY - minY
            }
        };
    }

    /*
     * Video drift correction. Drift is observed media time minus the
     * compensated target at the same instant: positive drift is a video that
     * is ahead and must slow down, negative drift must speed up.
     *
     *   |drift| <= 50 ms     deadband: rate 1, no seek
     *   50..250 ms           rate = 1 - drift * (0.02 / 250), clamped
     *   > 250 ms             one local seek, at most once per 5 s; while the
     *                        seek budget is spent the rate stays at its limit
     */
    var VIDEO_DEADBAND_MS = 50;
    var VIDEO_SEEK_MS = 250;
    var VIDEO_RATE_SPAN = 0.02;
    var VIDEO_SEEK_INTERVAL_MS = 5000;

    function videoDriftMs(mediaMs, targetMs) {
        return (
            finiteNumber(mediaMs, "media time") -
            finiteNumber(targetMs, "target time")
        );
    }

    function videoCorrection(options) {
        var drift = finiteNumber(options.driftMs, "drift");
        var magnitude = Math.abs(drift);
        if (magnitude <= VIDEO_DEADBAND_MS) return { rate: 1, seek: false };
        if (magnitude <= VIDEO_SEEK_MS) {
            var rate = 1 - drift * (VIDEO_RATE_SPAN / VIDEO_SEEK_MS);
            return {
                rate: Math.min(
                    1 + VIDEO_RATE_SPAN,
                    Math.max(1 - VIDEO_RATE_SPAN, rate)
                ),
                seek: false,
            };
        }
        var last = options.lastSeekMs;
        var due =
            last === null ||
            last === undefined ||
            finiteNumber(options.nowMs, "now") - last >= VIDEO_SEEK_INTERVAL_MS;
        if (due) return { rate: 1, seek: true };
        return { rate: 1 - (drift > 0 ? 1 : -1) * VIDEO_RATE_SPAN, seek: false };
    }

    var api = {
        IDENTITY: IDENTITY,
        multiply: multiply,
        inverse: inverse,
        apply: apply,
        translate: translate,
        scale: scale,
        rotate: rotate,
        quarterTurn: quarterTurn,
        bodyGeometry: bodyGeometry,
        fitMatrix: fitMatrix,
        panelToWall: panelToWall,
        normalizedSourceToPanel: normalizedSourceToPanel,
        cssToPanel: cssToPanel,
        backingScale: backingScale,
        canvasTransform: canvasTransform,
        canvasTransformComponents: canvasTransformComponents,
        videoDriftMs: videoDriftMs,
        videoCorrection: videoCorrection,
    };

    if (typeof window !== "undefined") window.TabletWallView = api;
    if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
