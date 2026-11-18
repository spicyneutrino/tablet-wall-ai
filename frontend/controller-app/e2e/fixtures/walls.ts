import type { WallLayout } from '../../src/stage/WallSvg';
import type { PanelProfile, PanelRect } from '../../src/domain/stagePanels';

type Colour = 'left' | 'right' | 'background';
export type WallFixture = {
  name: string;
  layout: WallLayout;
  profile?: PanelProfile;
  screens: Record<string, PanelRect & { cover: Colour; contain: Colour }>;
};

const profile = { active_width_mm: 80, active_height_mm: 120,
  bezels: { left: 10, top: 20, right: 30, bottom: 40 } };

export const walls: WallFixture[] = [
  {
    name: 'logical-grid-hole',
    layout: { kind: 'logical', width: 600, height: 400, placements: {
      a: { x: 0, y: 0, w: 200, h: 200, bezel: { left: 10, top: 20, right: 30, bottom: 40 } },
      b: { x: 200, y: 0, w: 200, h: 200, bezel: { left: 10, top: 20, right: 30, bottom: 40 } },
      c: { x: 400, y: 0, w: 200, h: 200, bezel: { left: 10, top: 20, right: 30, bottom: 40 } },
      d: { x: 0, y: 200, w: 200, h: 200, bezel: { left: 10, top: 20, right: 30, bottom: 40 } },
      e: { x: 200, y: 200, w: 200, h: 200, bezel: { left: 10, top: 20, right: 30, bottom: 40 } },
    } },
    // Screens start at cell+(10,20); size=(200-10-30,200-20-40)=(160,140). No sixth cell.
    // Image split x=300 in both fits; contain bands y=0..31.25 and 368.75..400.
    screens: {
      a: { x: 10, y: 20, width: 160, height: 140, cover: 'left', contain: 'left' },
      b: { x: 210, y: 20, width: 160, height: 140, cover: 'left', contain: 'left' },
      c: { x: 410, y: 20, width: 160, height: 140, cover: 'right', contain: 'right' },
      d: { x: 10, y: 220, width: 160, height: 140, cover: 'left', contain: 'left' },
      e: { x: 210, y: 220, width: 160, height: 140, cover: 'left', contain: 'left' },
    },
  },
  {
    name: 'logical-negative',
    layout: { kind: 'logical', width: 400, height: 300, placements: {
      a: { x: -20, y: 40, w: 120, h: 180, bezel: { left: 10, top: 20, right: 30, bottom: 40 } },
      b: { x: 260, y: 0, w: 120, h: 40, bezel: { left: 10, top: 2, right: 30, bottom: 8 } },
    } },
    // a=(-20+10,40+20,120-40,180-60). b=(260+10,0+2,120-40,40-10).
    // Split x=200; contain height=400*900/1600=225 starts at y=37.5, so b centre y=17 is a band.
    screens: {
      a: { x: -10, y: 60, width: 80, height: 120, cover: 'left', contain: 'left' },
      b: { x: 270, y: 2, width: 80, height: 30, cover: 'right', contain: 'background' },
    },
  },
  {
    name: 'physical-cardinal', profile,
    layout: { kind: 'physical', bounds: { x: 0, y: 0, width: 400, height: 400 }, slots: {
      a: { center_x_mm: 100, center_y_mm: 100, mount_angle: 0 },
      b: { center_x_mm: 300, center_y_mm: 100, mount_angle: 90 },
      c: { center_x_mm: 100, center_y_mm: 300, mount_angle: 180 },
      d: { center_x_mm: 300, center_y_mm: 300, mount_angle: 270 },
    } },
    // Body=120x180, active centre offset=(-10,-10). Rotate that offset to (-10,-10),(10,-10),(10,10),(-10,10).
    // Subtract half of 80x120 (0/180) or 120x80 (90/270). Split x=200; contain bands end at 87.5/312.5.
    screens: {
      a: { x: 50, y: 30, width: 80, height: 120, cover: 'left', contain: 'left' },
      b: { x: 250, y: 50, width: 120, height: 80, cover: 'right', contain: 'right' },
      c: { x: 70, y: 250, width: 80, height: 120, cover: 'left', contain: 'left' },
      d: { x: 230, y: 270, width: 120, height: 80, cover: 'right', contain: 'right' },
    },
  },
  {
    name: 'physical-37-nudge',
    profile: { active_width_mm: 100, active_height_mm: 60, bezels: { left: 10, top: 10, right: 10, bottom: 10 } },
    layout: { kind: 'physical', bounds: { x: 0, y: 0, width: 400, height: 300 }, slots: {
      a: { center_x_mm: 200, center_y_mm: 150, mount_angle: 37, nudge_x_mm: 15, nudge_y_mm: -5 },
    } },
    // Centre=(200+15,150-5)=(215,145). cos37=.7986355100, sin37=.6018150232.
    // AABB w=100*cos37+60*sin37=115.972452394, h=100*sin37+60*cos37=108.099632918.
    // x=215-w/2, y=145-h/2. Centre is right of split x=200 and inside contain y=37.5..262.5.
    screens: { a: { x: 157.013773803, y: 90.950183541, width: 115.972452394, height: 108.099632918,
      cover: 'right', contain: 'right' } },
  },
  {
    name: 'physical-negative-origin', profile,
    layout: { kind: 'physical', bounds: { x: -300, y: -200, width: 400, height: 300 }, slots: {
      a: { center_x_mm: -150, center_y_mm: -80, mount_angle: 0 },
    } },
    // Body top-left=(-150-60,-80-90); active=(-210+10,-170+20,80,120).
    // Split=-300+400/2=-100; contain y=-162.5..62.5, so centre (-160,-90) is left in both fits.
    screens: { a: { x: -200, y: -150, width: 80, height: 120, cover: 'left', contain: 'left' } },
  },
  {
    name: 'missing-profile',
    layout: { kind: 'physical', bounds: { x: 0, y: 0, width: 400, height: 300 },
      slots: { a: { center_x_mm: 200, center_y_mm: 150, profile_revision: 7 } } },
    // No pinned profile means no known screen dimensions, hence zero screen rectangles.
    screens: {},
  },
];
