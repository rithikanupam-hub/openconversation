// Premium vector motion-graphics film — light "paper" theme matching the site's illoca-style direction.
// Run from repo root with Swift and FFmpeg installed:
//   swift -module-cache-path /tmp/lingosync-swift-cache tests/site/render-film.swift
import Foundation
import CoreGraphics
import CoreText
import ImageIO

// MARK: - Fonts (registered from tests/site/fonts, .process scope; PostScript names printed for verification)
let fontsDir = URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent("tests/site/fonts")
@discardableResult
func registerFont(_ filename: String) -> String {
 let url = fontsDir.appendingPathComponent(filename)
 var errorRef: Unmanaged<CFError>?
 let ok = CTFontManagerRegisterFontsForURL(url as CFURL, .process, &errorRef)
 if !ok, let e = errorRef?.takeRetainedValue() { print("WARN: could not register \(filename): \(e)") }
 guard let descs = CTFontManagerCreateFontDescriptorsFromURL(url as CFURL) as? [CTFontDescriptor], let d = descs.first else {
  fatalError("No font descriptor for \(filename)")
 }
 let font = CTFontCreateWithFontDescriptor(d, 12, nil)
 let ps = CTFontCopyPostScriptName(font) as String
 print("Registered \(filename) -> PostScript name: \(ps)")
 return ps
}
let fSansRegular = registerFont("InstrumentSans-Regular.ttf")
let fSansMedium = registerFont("InstrumentSans-Medium.ttf")
let fSansSemiBold = registerFont("InstrumentSans-SemiBold.ttf")
let fSerifItalic = registerFont("InstrumentSerif-Italic.ttf")
let fMonoRegular = registerFont("JetBrainsMono-Regular.ttf")
let fMonoMedium = registerFont("JetBrainsMono-Medium.ttf")
let fCaveat = registerFont("Caveat-SemiBold.ttf")

let assets = URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent("frontend/site/assets")

let w = 1280, h = 720
let full = CGRect(x: 0, y: 0, width: CGFloat(w), height: CGFloat(h))
func makeBuffer() -> CGContext { CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4, space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)! }
let ctx = makeBuffer()
let bufA = makeBuffer()
let bufB = makeBuffer()
var target: CGContext = ctx

func color(_ r: CGFloat, _ g: CGFloat, _ b: CGFloat, _ a: CGFloat = 1) -> CGColor { CGColor(red: r / 255, green: g / 255, blue: b / 255, alpha: a) }

// MARK: - Palette — light paper theme, matching frontend/site/COPY.md
let paper = color(245, 243, 236)
let gridLine = color(230, 227, 214)
let ink = color(36, 39, 31)
let muted = color(111, 114, 102)
let orange = color(252, 96, 47)
let screenBg = color(20, 25, 19)
let screenText = color(238, 240, 228)
let sage = color(192, 215, 136)

func clamp01(_ x: Double) -> Double { min(1, max(0, x)) }
func easeInOutCubic(_ x: Double) -> Double { let p = clamp01(x); return p < 0.5 ? 4 * p * p * p : 1 - pow(-2 * p + 2, 3) / 2 }
func easeOutExpo(_ x: Double) -> Double { let p = clamp01(x); return p >= 1 ? 1 : 1 - pow(2, -10 * p) }

// MARK: - Drawing primitives
func text(_ value: String, _ x: CGFloat, _ y: CGFloat, _ size: CGFloat, _ fill: CGColor, _ font: String, _ alpha: CGFloat = 1, _ kern: CGFloat = 0) {
 target.saveGState(); target.setAlpha(alpha)
 var attrs: [NSAttributedString.Key: Any] = [NSAttributedString.Key(kCTFontAttributeName as String): CTFontCreateWithName(font as CFString, size, nil), NSAttributedString.Key(kCTForegroundColorAttributeName as String): fill]
 if kern != 0 { attrs[NSAttributedString.Key(kCTKernAttributeName as String)] = kern }
 let line = CTLineCreateWithAttributedString(NSAttributedString(string: value, attributes: attrs))
 target.textPosition = CGPoint(x: x, y: y); CTLineDraw(line, target); target.restoreGState()
}
func textWidth(_ value: String, _ size: CGFloat, _ font: String, _ kern: CGFloat = 0) -> CGFloat {
 var attrs: [NSAttributedString.Key: Any] = [NSAttributedString.Key(kCTFontAttributeName as String): CTFontCreateWithName(font as CFString, size, nil)]
 if kern != 0 { attrs[NSAttributedString.Key(kCTKernAttributeName as String)] = kern }
 let line = CTLineCreateWithAttributedString(NSAttributedString(string: value, attributes: attrs))
 return CTLineGetBoundsWithOptions(line, []).width
}
func box(_ x: CGFloat, _ y: CGFloat, _ width: CGFloat, _ height: CGFloat, _ fill: CGColor, _ radius: CGFloat = 12) {
 target.setFillColor(fill); target.addPath(CGPath(roundedRect: CGRect(x: x, y: y, width: width, height: height), cornerWidth: radius, cornerHeight: radius, transform: nil)); target.fillPath()
}
func strokeBox(_ x: CGFloat, _ y: CGFloat, _ width: CGFloat, _ height: CGFloat, _ stroke: CGColor, _ lineWidth: CGFloat = 1, _ radius: CGFloat = 12) {
 target.setStrokeColor(stroke); target.setLineWidth(lineWidth); target.addPath(CGPath(roundedRect: CGRect(x: x, y: y, width: width, height: height), cornerWidth: radius, cornerHeight: radius, transform: nil)); target.strokePath()
}
func waveSage(_ x: Double, _ y: Double, _ t: Double, _ count: Int, _ amp: Double = 13, _ c: CGColor = sage) {
 target.setStrokeColor(c); target.setLineWidth(2.4); target.setLineCap(.round)
 for i in 0..<count {
  let a = 3 + abs(sin(Double(i) * 0.5 + t * 2.1) * cos(Double(i) * 0.13 - t)) * amp
  target.move(to: CGPoint(x: x + Double(i) * 6, y: y - a)); target.addLine(to: CGPoint(x: x + Double(i) * 6, y: y + a)); target.strokePath()
 }
}
func drawAsterisk(_ cx: CGFloat, _ cy: CGFloat, _ r: CGFloat, _ c: CGColor, _ lw: CGFloat = 3.2) {
 target.setStrokeColor(c); target.setLineWidth(lw); target.setLineCap(.round)
 for i in 0..<3 {
  let a = Double(i) * Double.pi / 3
  target.move(to: CGPoint(x: cx - CGFloat(cos(a)) * r, y: cy - CGFloat(sin(a)) * r))
  target.addLine(to: CGPoint(x: cx + CGFloat(cos(a)) * r, y: cy + CGFloat(sin(a)) * r))
  target.strokePath()
 }
}
func circledNumber(_ n: Int, _ cx: CGFloat, _ cy: CGFloat, _ r: CGFloat, _ c: CGColor) {
 target.setStrokeColor(c); target.setLineWidth(1.3)
 target.addEllipse(in: CGRect(x: cx - r, y: cy - r, width: r * 2, height: r * 2)); target.strokePath()
 let s = "\(n)"
 let tw = textWidth(s, r * 1.05, fMonoMedium)
 text(s, cx - tw / 2, cy - r * 0.36, r * 1.05, c, fMonoMedium)
}
func handArrow(_ x0: CGFloat, _ y0: CGFloat, _ x1: CGFloat, _ y1: CGFloat, _ c: CGColor, _ wobble: Double = 0) {
 target.setStrokeColor(c); target.setLineWidth(2); target.setLineCap(.round); target.setLineJoin(.round)
 let mx = (x0 + x1) / 2 + CGFloat(sin(wobble) * 9), my = (y0 + y1) / 2 + CGFloat(cos(wobble * 1.4) * 7)
 target.move(to: CGPoint(x: x0, y: y0))
 target.addCurve(to: CGPoint(x: x1, y: y1), control1: CGPoint(x: mx - 10, y: my + 8), control2: CGPoint(x: mx + 8, y: my - 6))
 target.strokePath()
 let angle = atan2(Double(y1 - y0), Double(x1 - x0)); let ah = 8.0
 let p1 = CGPoint(x: x1 - CGFloat(ah * cos(angle - 0.4)), y: y1 - CGFloat(ah * sin(angle - 0.4)))
 let p2 = CGPoint(x: x1 - CGFloat(ah * cos(angle + 0.4)), y: y1 - CGFloat(ah * sin(angle + 0.4)))
 target.move(to: CGPoint(x: x1, y: y1)); target.addLine(to: p1)
 target.move(to: CGPoint(x: x1, y: y1)); target.addLine(to: p2)
 target.strokePath()
}
func deviceScreen(_ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat, _ radius: CGFloat = 12) {
 box(x, y, w, h, ink, radius)
 let pad: CGFloat = 9
 box(x + pad, y + pad, w - pad * 2, h - pad * 2, screenBg, max(2, radius - 6))
}
func laptopBase(_ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat) {
 box(x, y, w, h, color(232, 229, 217), 8)
 strokeBox(x, y, w, h, ink, 1, 8)
 target.setStrokeColor(color(36, 39, 31, 0.35)); target.setLineWidth(1)
 target.move(to: CGPoint(x: x + w / 2 - 30, y: y + h / 2)); target.addLine(to: CGPoint(x: x + w / 2 + 30, y: y + h / 2)); target.strokePath()
}

// MARK: - Scene schedule: 6 equal 6s scenes @ 24fps = 864 frames / 36.0s
let sceneCount = 6
let sceneLen = [144, 144, 144, 144, 144, 144]
var sceneStart = [Int](repeating: 0, count: sceneCount)
for i in 1..<sceneCount { sceneStart[i] = sceneStart[i - 1] + sceneLen[i - 1] }
let totalFrames = sceneStart[sceneCount - 1] + sceneLen[sceneCount - 1]

struct SceneMeta { let circleNum: Int?; let label: String; let title: String; let accent: String }
let scenes: [SceneMeta] = [
 SceneMeta(circleNum: nil, label: "VOCALGRID", title: "Good ideas.", accent: "Different languages."),
 SceneMeta(circleNum: 1, label: "LISTEN", title: "They speak.", accent: "In Italian, as usual."),
 SceneMeta(circleNum: 2, label: "TRANSLATE", title: "It translates.", accent: "Phrase by phrase."),
 SceneMeta(circleNum: 3, label: "HEAR · voice matching with consent", title: "You hear it.", accent: "In English. In a familiar voice."),
 SceneMeta(circleNum: nil, label: "LANGUAGES · Italian → English tested today", title: "Many languages.", accent: "One conversation."),
 SceneMeta(circleNum: nil, label: "EARLY ACCESS", title: "vocalgrid", accent: "Still connected."),
]

// MARK: - Stage: the framed illustration rectangle (like illoca.unseen.co)
let stageRect = CGRect(x: 678, y: 128, width: 542, height: 462)
func drawStageFrame() {
 target.setStrokeColor(color(36, 39, 31, 0.85)); target.setLineWidth(1)
 target.addPath(CGPath(roundedRect: stageRect, cornerWidth: 16, cornerHeight: 16, transform: nil))
 target.strokePath()
}
func paperBackground(_ frame: Int) {
 target.setFillColor(paper); target.fill(full)
 target.setStrokeColor(gridLine); target.setLineWidth(1)
 var gx: CGFloat = 0
 while gx <= 1280 { target.move(to: CGPoint(x: gx, y: 0)); target.addLine(to: CGPoint(x: gx, y: 720)); target.strokePath(); gx += 24 }
 var gy: CGFloat = 0
 while gy <= 720 { target.move(to: CGPoint(x: 0, y: gy)); target.addLine(to: CGPoint(x: 1280, y: gy)); target.strokePath(); gy += 24 }
}
func grain(_ frame: Int) {
 var seed = UInt64(bitPattern: Int64(9000 + frame))
 func nextRand() -> Double { seed = seed &* 6364136223846793005 &+ 1442695040888963407; return Double(seed >> 11) / Double(1 << 53) }
 target.saveGState()
 for _ in 0..<130 {
  let gx = CGFloat(nextRand() * 1280), gy = CGFloat(nextRand() * 720)
  target.setFillColor(nextRand() > 0.5 ? color(36, 39, 31, 0.035) : color(255, 255, 255, 0.05))
  target.fill(CGRect(x: gx, y: gy, width: 1.2, height: 1.2))
 }
 target.restoreGState()
}

// MARK: - Panels (illustrated content inside the stage rect)
func panelOpening(_ frame: Int) {
 let t = Double(frame) / 24
 let ix = stageRect.minX + 24, iy = stageRect.minY + 24, iw = stageRect.width - 48
 text("EUROPEAN LANGUAGES · ITALIAN → ENGLISH TODAY", ix, iy + 4, 10.5, muted, fMonoMedium, 1, 0.6)
 laptopBase(ix, iy + 26, iw, 38)
 let screenH: CGFloat = 300, screenY = iy + 26 + 38 + 12
 deviceScreen(ix, screenY, iw, screenH, 18)
 let wmSize: CGFloat = 32
 text("vocalgrid", ix + 36, screenY + screenH - 86, wmSize, screenText, fSansSemiBold)
 drawAsterisk(ix + 36 + textWidth("vocalgrid", wmSize, fSansSemiBold) + 28, screenY + screenH - 86 + 12, 12, orange, 2.8)
 text("SPOKEN TRANSLATION", ix + 36, screenY + screenH - 118, 11, color(170, 176, 158, 1), fMonoMedium, 1, 1.6)
 waveSage(Double(ix + 36), Double(screenY + 62), t, 58, 15)
}
func panelListen(_ frame: Int) {
 let t = Double(frame) / 24
 let ix = stageRect.minX + 24, iy = stageRect.minY + 24, iw = stageRect.width - 48
 laptopBase(ix, iy, iw, 34)
 let screenH: CGFloat = 280, screenY = iy + 34 + 14
 deviceScreen(ix, screenY, iw, screenH, 18)
 let tileW: CGFloat = (iw - 18 * 2 - 16) / 2, tileH: CGFloat = 88
 let tileY = screenY + 18
 box(ix + 18, tileY, tileW, tileH, color(52, 58, 44), 10)
 text("GM", ix + 18 + 18, tileY + tileH / 2 - 9, 20, screenText, fSansMedium)
 box(ix + 18 + tileW + 16, tileY, tileW, tileH, orange, 10)
 text("YOU", ix + 18 + tileW + 16 + 18, tileY + tileH / 2 - 9, 20, ink, fSansMedium)
 waveSage(Double(ix + 18), Double(tileY + tileH + 30), t, 56, 8)
 let chipH: CGFloat = 64, chipY = screenY + screenH - 18 - chipH
 box(ix + 18, chipY, iw - 36, chipH, color(30, 36, 26), 10)
 text("IT", ix + 34, chipY + chipH - 22, 10.5, color(170, 176, 158, 1), fMonoMedium, 1, 1.4)
 text("Possiamo condividere l’idea venerdì.", ix + 34, chipY + 16, 17, screenText, fSansMedium)
 text("just talk normally", ix + 40, screenY + screenH + 40, 22, ink, fCaveat)
 handArrow(ix + iw - 60, screenY + screenH + 50, ix + iw - 140, screenY + screenH + 10, ink, 1.4)
}
func panelTranslate(_ frame: Int) {
 let localFrame = frame - sceneStart[2]
 let ix = stageRect.minX + 24, iy = stageRect.minY + 24, iw = stageRect.width - 48
 let chipW = iw * 0.6
 let phrases: [(String, String)] = [("Possiamo condividere", "We can share"), ("l’idea", "the idea"), ("venerdì.", "on Friday.")]
 let chipH: CGFloat = 72, gap: CGFloat = 16
 let totalH = chipH * 3 + gap * 2
 let startY = iy + (stageRect.height - 48 - totalH - 40) / 2 + 40
 let starts = [24, 56, 88]; let flipLen = 20
 var chipYs: [CGFloat] = []
 for i in 0..<3 { chipYs.append(startY + CGFloat(2 - i) * (chipH + gap)) }
 for i in 0..<3 {
  let y = chipYs[i]
  box(ix, y, chipW, chipH, screenBg, 12)
  let p = clamp01(Double(localFrame - starts[i]) / Double(flipLen))
  let showFrom = p < 0.5
  let sxScale: CGFloat = showFrom ? CGFloat(1 - easeInOutCubic(p / 0.5)) : CGFloat(easeInOutCubic((p - 0.5) / 0.5))
  let label = showFrom ? phrases[i].0 : phrases[i].1
  target.saveGState()
  target.translateBy(x: ix + chipW / 2, y: y + chipH / 2)
  target.scaleBy(x: max(0.03, sxScale), y: 1)
  target.translateBy(x: -(ix + chipW / 2), y: -(y + chipH / 2))
  text(label, ix + 22, y + chipH / 2 - 8, 18, screenText, fSansMedium)
  target.restoreGState()
  text(showFrom ? "IT" : "EN", ix + chipW - 42, y + chipH - 20, 10, showFrom ? color(150, 156, 138, 1) : sage, fMonoMedium, 1, 1.2)
 }
 let doneAt = starts[2] + flipLen
 let ap = clamp01(Double(localFrame - doneAt - 8) / 18.0)
 if ap > 0 {
  target.saveGState(); target.setAlpha(CGFloat(ap))
  text("We can share the idea on Friday.", ix, chipYs[2] - 34, 17, ink, fSerifItalic)
  target.restoreGState()
 }
 let noteX = ix + chipW + 22
 let topY = chipYs[0]
 text("phrase by phrase,", noteX, topY + chipH * 0.62, 18, ink, fCaveat)
 text("not word by word", noteX, topY + chipH * 0.62 - 22, 18, ink, fCaveat)
 handArrow(noteX + 6, topY + chipH * 0.68, ix + chipW + 6, topY + chipH * 0.5, ink, 0.9)
}
func panelHear(_ frame: Int) {
 let t = Double(frame) / 24
 let ix = stageRect.minX + 24, iy = stageRect.minY + 24, iw = stageRect.width - 48, ih = stageRect.height - 48
 let hx = ix + 70, hy = iy + ih * 0.5
 target.setStrokeColor(ink); target.setLineWidth(10); target.setLineCap(.round)
 target.addArc(center: CGPoint(x: hx, y: hy), radius: 70, startAngle: .pi * 0.12, endAngle: .pi * 0.88, clockwise: false)
 target.strokePath()
 box(hx - 84, hy - 24, 26, 60, ink, 10)
 box(hx + 58, hy - 24, 26, 60, ink, 10)
 box(hx - 78, hy - 14, 16, 40, orange, 6)
 box(hx + 64, hy - 14, 16, 40, orange, 6)
 let scrX = ix + 180, scrW = iw - 180, scrH: CGFloat = 210, scrY = iy + ih / 2 - scrH / 2
 deviceScreen(scrX, scrY, scrW, scrH, 16)
 text("EN", scrX + 26, scrY + scrH - 34, 10.5, sage, fMonoMedium, 1, 1.4)
 text("We can share the idea", scrX + 26, scrY + scrH - 64, 19, screenText, fSansMedium)
 text("on Friday.", scrX + 26, scrY + scrH - 92, 19, screenText, fSansMedium)
 waveSage(Double(scrX + 26), Double(scrY + 40), t, 40, 13)
 text("only with their consent", ix + 10, iy + ih - 30, 21, ink, fCaveat)
 handArrow(ix + 150, iy + ih - 24, hx + 20, hy + 60, ink, 1.1)
}
func rollSlot(_ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat, _ oldText: String, _ newText: String, _ progress: Double) {
 box(x, y, w, h, paper, 10)
 strokeBox(x, y, w, h, color(36, 39, 31, 0.25), 1, 10)
 target.saveGState()
 target.addPath(CGPath(rect: CGRect(x: x + 6, y: y + 4, width: w - 12, height: h - 8), transform: nil)); target.clip()
 if progress < 1 {
  text(oldText, x + 16, y + h * 0.32 + CGFloat(progress) * h, 18, ink, fSansMedium)
  text(newText, x + 16, y + h * 0.32 - CGFloat(1 - progress) * h, 18, ink, fSansMedium)
 } else {
  text(newText, x + 16, y + h * 0.32, 18, ink, fSansMedium)
 }
 target.restoreGState()
}
let langPairs: [(String, String)] = [("Italiano", "English"), ("Deutsch", "English"), ("Français", "English"), ("Svenska", "English"), ("Dansk", "English"), ("Español", "English"), ("Nederlands", "English"), ("Português", "English"), ("English", "Italiano")]
func panelLanguages(_ frame: Int) {
 let ix = stageRect.minX + 24, iy = stageRect.minY + 24, iw = stageRect.width - 48, ih = stageRect.height - 48
 let localFrame = frame - sceneStart[4]
 let perItem = 144 / langPairs.count
 var itemIndex = localFrame / perItem
 if itemIndex > langPairs.count - 1 { itemIndex = langPairs.count - 1 }
 let within = localFrame - itemIndex * perItem
 let rollLen = 12
 let rollP = easeInOutCubic(Double(within) / Double(rollLen))
 let cur = langPairs[itemIndex]
 let prev = itemIndex > 0 ? langPairs[itemIndex - 1] : cur
 let leftChanged = itemIndex > 0 && prev.0 != cur.0
 let rightChanged = itemIndex > 0 && prev.1 != cur.1
 let panelY = iy + ih * 0.5 - 90
 let screenW = iw, screenH: CGFloat = 180
 deviceScreen(ix, panelY, screenW, screenH, 16)
 text("LIVE ROUTING PREVIEW", ix + 28, panelY + screenH - 30, 10.5, orange, fMonoMedium, 1, 1.4)
 let slotW: CGFloat = 170, slotH: CGFloat = 52
 let leftX = ix + 30, rightX = ix + screenW - 30 - slotW, slotY = panelY + screenH / 2 - slotH / 2 - 6
 rollSlot(leftX, slotY, slotW, slotH, prev.0, cur.0, leftChanged && within < rollLen ? rollP : 1)
 rollSlot(rightX, slotY, slotW, slotH, prev.1, cur.1, rightChanged && within < rollLen ? rollP : 1)
 text("→", ix + screenW / 2 - 9, slotY + 13, 26, orange, fSansSemiBold)
 let dotsY = panelY + 18
 for i in 0..<langPairs.count {
  let dx = ix + 30 + CGFloat(i) * (screenW - 60) / CGFloat(langPairs.count - 1)
  target.setFillColor(i == itemIndex ? orange : color(150, 156, 138, 0.55))
  target.fillEllipse(in: CGRect(x: dx, y: dotsY, width: 7, height: 7))
 }
 text("Italian → English tested today · other pairs in validation", ix, panelY - 34, 12.5, muted, fMonoMedium, 1, 0.3)
}
func panelEnding(_ frame: Int) {
 let t = Double(frame) / 24
 let cx = stageRect.midX, cy = stageRect.midY
 for i in 0..<3 {
  let r = 60 + CGFloat(i) * 38 + CGFloat(sin(t * 0.6 + Double(i)) * 3)
  let a = max(0.05, 0.18 - Double(i) * 0.05)
  target.setStrokeColor(color(252, 96, 47, CGFloat(a))); target.setLineWidth(1.2)
  target.addEllipse(in: CGRect(x: cx - r, y: cy - r, width: r * 2, height: r * 2))
  target.strokePath()
 }
 drawAsterisk(cx, cy, 46, orange, 6)
}
func panel(_ idx: Int, _ frame: Int) {
 switch idx {
 case 0: panelOpening(frame)
 case 1: panelListen(frame)
 case 2: panelTranslate(frame)
 case 3: panelHear(frame)
 case 4: panelLanguages(frame)
 default: panelEnding(frame)
 }
}

// MARK: - Title block: masked line-by-line rise, independent of panel transitions (never splices sentences)
func riseLine(_ value: String, _ x: CGFloat, _ yBase: CGFloat, _ size: CGFloat, _ fill: CGColor, _ font: String, _ localFrame: Int, _ startDelay: Int, _ dur: Int = 20) {
 let lf = localFrame - startDelay
 if lf < -2 { return }
 let p = clamp01(Double(lf) / Double(dur))
 let e = easeOutExpo(p)
 let rise: CGFloat = size * 1.1
 let dy = CGFloat(1 - e) * rise
 target.saveGState()
 let boxY = yBase - size * 0.34, boxH = size * 1.15
 target.addPath(CGPath(rect: CGRect(x: x - 6, y: boxY, width: 1180, height: boxH), transform: nil)); target.clip()
 text(value, x, yBase - dy, size, fill, font)
 target.restoreGState()
}
func titleBlock(_ idx: Int, _ localFrame: Int) {
 let s = scenes[idx]
 let x: CGFloat = 64
 let titleSize: CGFloat = idx == 5 ? 46 : 54, accentSize: CGFloat = idx == 5 ? 42 : 50
 let labelY: CGFloat = 520, titleY: CGFloat = 420, accentY: CGFloat = 338
 if localFrame >= -2 {
  let p = clamp01(Double(localFrame) / 18.0); let e = easeOutExpo(p); let dy = CGFloat(1 - e) * 14
  target.saveGState()
  target.addPath(CGPath(rect: CGRect(x: x - 10, y: labelY - 16, width: 900, height: 36), transform: nil)); target.clip()
  var lx = x
  if let n = s.circleNum { circledNumber(n, lx + 9, labelY - dy + 3.5, 9, orange); lx += 27 }
  text(s.label, lx, labelY - dy, 13, muted, fMonoMedium, 1, 1.6)
  target.restoreGState()
 }
 riseLine(s.title, x, titleY, titleSize, ink, fSansSemiBold, localFrame, 2, 20)
 if idx == 5 {
  let ap = clamp01(Double(localFrame - 2) / 20.0)
  if ap > 0.2 {
   let tw = textWidth(s.title, titleSize, fSansSemiBold)
   target.saveGState(); target.setAlpha(CGFloat(clamp01((ap - 0.2) * 3)))
   drawAsterisk(x + tw + 32, titleY + 16, 15, orange, 3.4)
   target.restoreGState()
  }
 }
 riseLine(s.accent, x, accentY, accentSize, orange, fSerifItalic, localFrame, 4, 20)
}

// MARK: - Header / footer chrome
func overlay(_ frame: Int, _ idx: Int) {
 text("vocalgrid", 60, 654, 20, ink, fSansSemiBold)
 drawAsterisk(60 + textWidth("vocalgrid", 20, fSansSemiBold) + 18, 654 + 9, 8, orange, 2.2)
 let tag = "SPOKEN TRANSLATION · CONCEPT FILM"
 text(tag, 1216 - textWidth(tag, 10, fMonoMedium, 1.2), 660, 10, muted, fMonoMedium, 1, 1.2)
 text("PRODUCT CONCEPT · ILLUSTRATIVE SCENARIOS", 64, 40, 10, muted, fMonoMedium, 1, 0.8)
 let idxLabel = String(format: "%02d / 06", idx + 1)
 text(idxLabel, 1216 - textWidth(idxLabel, 11, fMonoMedium, 1), 40, 11, muted, fMonoMedium, 1, 1)
 box(64, 26, 1152, 2, color(230, 227, 214, 1), 0)
 let progress = Double(frame) / Double(totalFrames - 1)
 box(64, 26, 1152 * CGFloat(progress), 2, orange, 0)
}

// MARK: - Signature transition: stage push (panel), iris (final logo only)
func drawShifted(_ img: CGImage, _ dx: CGFloat, _ scale: CGFloat) {
 ctx.saveGState()
 ctx.translateBy(x: stageRect.midX + dx, y: stageRect.midY)
 ctx.scaleBy(x: scale, y: scale)
 ctx.translateBy(x: -stageRect.midX, y: -stageRect.midY)
 ctx.draw(img, in: full)
 ctx.restoreGState()
}
func irisComposite(_ progress: Double, _ imgA: CGImage, _ imgB: CGImage) {
 let e = easeOutExpo(progress)
 ctx.draw(imgA, in: full)
 let cx = stageRect.midX, cy = stageRect.midY, maxR: CGFloat = 760
 let r = CGFloat(e) * maxR
 ctx.saveGState(); ctx.addEllipse(in: CGRect(x: cx - r, y: cy - r, width: r * 2, height: r * 2)); ctx.clip(); ctx.draw(imgB, in: full); ctx.restoreGState()
 if progress < 1 { ctx.setStrokeColor(color(252, 96, 47, 0.5 * (1 - progress))); ctx.setLineWidth(3); ctx.addEllipse(in: CGRect(x: cx - r, y: cy - r, width: r * 2, height: r * 2)); ctx.strokePath() }
}

// MARK: - Encode
let process = Process(); process.executableURL = URL(fileURLWithPath: "/opt/homebrew/bin/ffmpeg")
process.arguments = ["-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pixel_format", "rgba", "-video_size", "1280x720", "-framerate", "24", "-i", "pipe:0", "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "21", "-pix_fmt", "yuv420p", "-movflags", "+faststart", assets.appendingPathComponent("conversation-film.mp4").path]
let pipe = Pipe(); process.standardInput = pipe; try process.run()

let transitionLen = 18
let irisLen = 22

for frame in 0..<totalFrames {
 var idx = 0
 while idx < sceneCount - 1 && frame >= sceneStart[idx + 1] { idx += 1 }
 let localFrame = frame - sceneStart[idx]
 let tLen = idx == 5 ? irisLen : transitionLen
 let inTransition = idx > 0 && localFrame < tLen

 target = ctx
 paperBackground(frame)

 if inTransition && idx != 5 {
  let progress = Double(localFrame) / Double(tLen)
  bufA.clear(full); target = bufA; panel(idx - 1, frame)
  bufB.clear(full); target = bufB; panel(idx, frame)
  target = ctx
  ctx.saveGState()
  ctx.addPath(CGPath(roundedRect: stageRect, cornerWidth: 16, cornerHeight: 16, transform: nil)); ctx.clip()
  let e = easeInOutCubic(progress)
  drawShifted(bufA.makeImage()!, -CGFloat(e) * stageRect.width, 1 - 0.03 * CGFloat(e))
  drawShifted(bufB.makeImage()!, CGFloat(1 - e) * stageRect.width, 0.97 + 0.03 * CGFloat(e))
  ctx.restoreGState()
  drawStageFrame()
  ctx.setFillColor(orange)
  ctx.fill(CGRect(x: stageRect.minX, y: stageRect.minY - 9, width: stageRect.width * CGFloat(progress), height: 3))
 } else if inTransition && idx == 5 {
  let progress = Double(localFrame) / Double(tLen)
  bufA.clear(full); target = bufA; paperBackground(frame); panel(4, frame); drawStageFrame()
  bufB.clear(full); target = bufB; paperBackground(frame); panel(5, frame); drawStageFrame()
  target = ctx
  irisComposite(progress, bufA.makeImage()!, bufB.makeImage()!)
 } else {
  panel(idx, frame)
  drawStageFrame()
 }

 target = ctx
 titleBlock(idx, localFrame)
 overlay(frame, idx)
 grain(frame)
 try pipe.fileHandleForWriting.write(contentsOf: Data(bytes: ctx.data!, count: w * h * 4))
}
try pipe.fileHandleForWriting.close(); process.waitUntilExit()
assert(process.terminationStatus == 0, "Encoding failed")
print("Rendered \(totalFrames) frames / \(Double(totalFrames) / 24) seconds.")
