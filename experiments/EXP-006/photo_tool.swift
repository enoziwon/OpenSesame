// EXP-006 사진 정리 도구 (macOS 전용). 보통은 intake.py가 부른다.
//
//   swift experiments/EXP-006/photo_tool.swift <원본 폴더> <정리 폴더>
//
// - 원본 사진(HEIC·JPG·PNG)을 찍은 시각 순서로 001.jpg, 002.jpg …로 저장한다. 원본은 건드리지 않는다.
// - 방향(회전)은 픽셀에 반영하고, 위치·기기·시각 같은 메타데이터는 새 파일에 쓰지 않는다.
//   이 파일이 CLOVA로 가므로 위치 정보가 밖으로 나가지 않는다.
// - 앱 서버가 받는 크기(10MB)를 넘으면 긴 변 4032px로 줄인다.
// - 맥 내장 OCR(Vision)로 읽은 줄을 stage.json에 남긴다. 품목보고번호를 찾아 정리하는 데만 쓴다.
//   실험 입력 글자는 CLOVA(run_raw.py)다.
// - 12장씩 모아 보기(sheet_01.jpg …)를 만든다. 사진 번호가 왼쪽 위에 찍힌다.

import CoreText
import Foundation
import ImageIO
import UniformTypeIdentifiers
import Vision

let maxBytes = 10 * 1024 * 1024
let shrinkSide = 4032
let imageExts: Set<String> = ["heic", "heif", "jpg", "jpeg", "png"]

func warn(_ message: String) {
    FileHandle.standardError.write((message + "\n").data(using: .utf8)!)
}

func properties(_ src: CGImageSource) -> [String: Any] {
    return (CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [String: Any]) ?? [:]
}

// 찍은 시각: EXIF DateTimeOriginal, 없으면 TIFF DateTime, 둘 다 없으면 빈 글자
func takenTime(_ props: [String: Any]) -> String {
    if let exif = props[kCGImagePropertyExifDictionary as String] as? [String: Any],
       let t = exif[kCGImagePropertyExifDateTimeOriginal as String] as? String { return t }
    if let tiff = props[kCGImagePropertyTIFFDictionary as String] as? [String: Any],
       let t = tiff[kCGImagePropertyTIFFDateTime as String] as? String { return t }
    return ""
}

// 방향을 반영한 이미지. maxSide가 원본보다 크면 원본 크기 그대로
func orientedImage(_ src: CGImageSource, maxSide: Int) -> CGImage? {
    let opts: [CFString: Any] = [
        kCGImageSourceCreateThumbnailFromImageAlways: true,
        kCGImageSourceCreateThumbnailWithTransform: true,
        kCGImageSourceThumbnailMaxPixelSize: maxSide,
    ]
    return CGImageSourceCreateThumbnailAtIndex(src, 0, opts as CFDictionary)
}

// 메타데이터 없이 JPEG로 (압축 품질만 넘긴다)
func jpegData(_ image: CGImage, quality: Double) -> Data? {
    let data = NSMutableData()
    guard let dest = CGImageDestinationCreateWithData(data, UTType.jpeg.identifier as CFString, 1, nil) else {
        return nil
    }
    CGImageDestinationAddImage(dest, image, [kCGImageDestinationLossyCompressionQuality: quality] as CFDictionary)
    return CGImageDestinationFinalize(dest) ? data as Data : nil
}

// 맥 내장 OCR. 위에서 아래, 왼쪽에서 오른쪽 순서로 줄을 돌려준다
func ocrLines(_ image: CGImage) throws -> [String] {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["ko-KR", "en-US"]
    request.usesLanguageCorrection = false
    try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
    let found = (request.results ?? []).sorted {
        let a = (-($0.boundingBox.midY * 100).rounded(), $0.boundingBox.minX)
        let b = (-($1.boundingBox.midY * 100).rounded(), $1.boundingBox.minX)
        return a < b
    }
    return found.compactMap { $0.topCandidates(1).first?.string }
}

// 모아 보기 한 장: 4열 3행. 칸 위쪽 띠에 사진 번호, 그 아래에 사진(회색 테두리)
func writeSheet(_ items: [(String, CGImage)], to url: URL) throws {
    let cols = 4, rows = 3, cellW = 420, cellH = 600, labelH = 60.0, pad = 8.0
    let width = cols * cellW, height = rows * cellH
    guard let space = CGColorSpace(name: CGColorSpace.sRGB),
          let ctx = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
                              space: space, bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else {
        throw NSError(domain: "sheet", code: 1, userInfo: [NSLocalizedDescriptionKey: "그림판을 만들 수 없다"])
    }
    ctx.setFillColor(CGColor(gray: 1, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: width, height: height))
    let font = CTFontCreateWithName("Helvetica-Bold" as CFString, 44, nil)
    let attrs: [NSAttributedString.Key: Any] = [
        NSAttributedString.Key(kCTFontAttributeName as String): font,
        NSAttributedString.Key(kCTForegroundColorAttributeName as String): CGColor(red: 0.85, green: 0, blue: 0, alpha: 1),
    ]
    for (i, (label, image)) in items.enumerated() {
        let x0 = Double((i % cols) * cellW), y0 = Double(height - (i / cols + 1) * cellH)  // 칸의 왼쪽 아래
        let boxW = Double(cellW) - 2 * pad, boxH = Double(cellH) - labelH - 2 * pad
        let scale = min(boxW / Double(image.width), boxH / Double(image.height))
        let w = Double(image.width) * scale, h = Double(image.height) * scale
        let rect = CGRect(x: x0 + pad + (boxW - w) / 2, y: y0 + pad + (boxH - h) / 2, width: w, height: h)
        ctx.draw(image, in: rect)
        ctx.setStrokeColor(CGColor(gray: 0.6, alpha: 1))
        ctx.setLineWidth(2)
        ctx.stroke(rect)
        ctx.textPosition = CGPoint(x: x0 + pad + 4, y: y0 + Double(cellH) - labelH + 10)
        CTLineDraw(CTLineCreateWithAttributedString(NSAttributedString(string: label, attributes: attrs)), ctx)
    }
    guard let sheet = ctx.makeImage(), let data = jpegData(sheet, quality: 0.8) else {
        throw NSError(domain: "sheet", code: 2, userInfo: [NSLocalizedDescriptionKey: "모아 보기를 저장할 수 없다"])
    }
    try data.write(to: url)
}

// 사진 한 장 정리: (stage.json 기록, 모아 보기용 작은 그림)
func stageOne(_ src: CGImageSource, name: String, taken: String, no: String, outDir: URL) throws -> ([String: Any], CGImage?) {
    let props = properties(src)
    let fullSide = max(props[kCGImagePropertyPixelWidth as String] as? Int ?? 0,
                       props[kCGImagePropertyPixelHeight as String] as? Int ?? 0)
    guard var image = orientedImage(src, maxSide: max(fullSide, 1)), var data = jpegData(image, quality: 0.9) else {
        throw NSError(domain: "stage", code: 1, userInfo: [NSLocalizedDescriptionKey: "\(name): 열 수 없다"])
    }
    var shrunk = false
    if data.count > maxBytes, let small = orientedImage(src, maxSide: shrinkSide), let smallData = jpegData(small, quality: 0.9) {
        image = small
        data = smallData
        shrunk = true
    }
    try data.write(to: outDir.appendingPathComponent("\(no).jpg"))
    let lines = try ocrLines(image)
    let record: [String: Any] = [
        "no": no, "source": name, "taken": taken, "width": image.width, "height": image.height,
        "bytes": data.count, "shrunk": shrunk, "lines": lines,
    ]
    return (record, orientedImage(src, maxSide: 600))
}

func main() -> Int32 {
    let args = CommandLine.arguments
    guard args.count == 3 else {
        warn("사용법: swift photo_tool.swift <원본 폴더> <정리 폴더>")
        return 2
    }
    let srcDir = URL(fileURLWithPath: args[1]), outDir = URL(fileURLWithPath: args[2])
    let files: [URL]
    do {
        try FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)
        files = try FileManager.default.contentsOfDirectory(at: srcDir, includingPropertiesForKeys: nil)
            .filter { imageExts.contains($0.pathExtension.lowercased()) && !$0.lastPathComponent.hasPrefix(".") }
    } catch {
        warn("폴더를 열 수 없다: \(error.localizedDescription)")
        return 1
    }
    var shots: [(name: String, taken: String, src: CGImageSource)] = []
    var records: [[String: Any]] = []
    for file in files {
        guard let src = CGImageSourceCreateWithURL(file as CFURL, nil) else {
            records.append(["no": "", "source": file.lastPathComponent, "error": "열 수 없다"])
            continue
        }
        shots.append((file.lastPathComponent, takenTime(properties(src)), src))
    }
    shots.sort { ($0.taken, $0.name) < ($1.taken, $1.name) }  // 찍은 시각, 같으면 파일 이름(IMG_0001 …) 순서
    var thumbs: [(String, CGImage)] = []
    for (i, shot) in shots.enumerated() {
        let no = String(format: "%03d", i + 1)
        do {
            let (record, thumb) = try stageOne(shot.src, name: shot.name, taken: shot.taken, no: no, outDir: outDir)
            records.append(record)
            if let thumb = thumb { thumbs.append((no, thumb)) }
            print("\(no)  \(shot.name)  줄 \((record["lines"] as? [String])?.count ?? 0)")
        } catch {
            records.append(["no": no, "source": shot.name, "error": error.localizedDescription])
            warn("\(no) \(shot.name): \(error.localizedDescription)")
        }
    }
    do {
        for start in stride(from: 0, to: thumbs.count, by: 12) {
            let name = String(format: "sheet_%02d.jpg", start / 12 + 1)
            try writeSheet(Array(thumbs[start..<min(start + 12, thumbs.count)]), to: outDir.appendingPathComponent(name))
        }
        let json = try JSONSerialization.data(withJSONObject: records, options: [.prettyPrinted, .sortedKeys])
        try json.write(to: outDir.appendingPathComponent("stage.json"))
    } catch {
        warn("저장 실패: \(error.localizedDescription)")
        return 1
    }
    return records.contains { $0["error"] != nil } ? 1 : 0
}

exit(main())
