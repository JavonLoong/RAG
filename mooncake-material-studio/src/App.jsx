import { useEffect, useMemo, useRef, useState } from "react";
import {
  Box,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Download,
  Grid3X3,
  Hand,
  Image,
  Layers,
  Link,
  Maximize,
  Palette,
  Printer,
  Redo2,
  RefreshCw,
  Ruler,
  Save,
  SlidersHorizontal,
  Sparkles,
  Sun,
  Type,
  Undo2,
  Upload,
} from "lucide-react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFExporter } from "three/examples/jsm/exporters/GLTFExporter.js";
import { STLExporter } from "three/examples/jsm/exporters/STLExporter.js";
import { calculatePrintStats, createMoldGroup } from "./moldModel.js";

const edgeOptions = [
  { id: "wave", label: "波浪" },
  { id: "straight", label: "直边" },
  { id: "flower", label: "花边" },
  { id: "pentagon", label: "梅花" },
  { id: "rounded", label: "圆角" },
];

const patterns = [
  { id: "lotus", label: "推荐花纹" },
  { id: "classic", label: "传统纹样" },
  { id: "geometric", label: "几何图案" },
  { id: "festival", label: "节日主题" },
  { id: "custom", label: "自定义上传" },
];

const defaultParams = {
  activeTab: "shape",
  view: "product",
  edgeStyle: "wave",
  diameter: 85,
  height: 25,
  dome: 0.6,
  scallopDepth: 0.5,
  scallopCount: 16,
  pattern: "lotus",
  patternDepth: 1.2,
  detailQuality: "high",
  text: "",
  font: "思源黑体",
  textDepth: 0.6,
  material: "cream",
  lights: true,
  grid: false,
};

function useDebouncedMessage() {
  const [message, setMessage] = useState("模型已保存");

  function flash(nextMessage) {
    setMessage(nextMessage);
    window.clearTimeout(flash.timer);
    flash.timer = window.setTimeout(() => setMessage("模型已保存"), 1800);
  }

  return [message, flash];
}

function Header({ params, update, exportDesign }) {
  const tabs = [
    { id: "shape", label: "外形", icon: Box },
    { id: "pattern", label: "花纹", icon: Sparkles },
    { id: "text", label: "刻字", icon: Type },
    { id: "print", label: "打印", icon: Printer },
  ];

  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark">
          <Sparkles size={27} strokeWidth={2.1} />
        </div>
        <div>
          <strong>MoonCake Studio</strong>
          <span>3D 月饼模具设计器</span>
        </div>
      </div>

      <nav className="workflow-tabs" aria-label="设计流程">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              className={params.activeTab === tab.id ? "active" : ""}
              key={tab.id}
              onClick={() => update({ activeTab: tab.id })}
              type="button"
            >
              <Icon size={19} />
              {tab.label}
            </button>
          );
        })}
      </nav>

      <div className="header-actions">
        <div className="view-switch" aria-label="预览模式">
          <button
            className={params.view === "product" ? "selected" : ""}
            onClick={() => update({ view: "product" })}
            type="button"
          >
            成品
          </button>
          <button
            className={params.view === "mold" ? "selected" : ""}
            onClick={() => update({ view: "mold" })}
            type="button"
          >
            模具
          </button>
        </div>
        <button className="icon-button ghost" type="button" aria-label="撤销">
          <Undo2 size={19} />
        </button>
        <button className="icon-button ghost" type="button" aria-label="重做">
          <Redo2 size={19} />
        </button>
        <button className="export-secondary" type="button" onClick={() => exportDesign("stl")}>
          <Download size={19} />
          STL
        </button>
        <button className="export-primary top-export" type="button" onClick={() => exportDesign("glb")}>
          <Box size={19} />
          GLB
        </button>
      </div>
    </header>
  );
}

function MoldViewport({ params, update, flash }) {
  const hostRef = useRef(null);
  const sceneRef = useRef(null);
  const rendererRef = useRef(null);
  const cameraRef = useRef(null);
  const controlsRef = useRef(null);
  const modelRef = useRef(null);
  const gridRef = useRef(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#cbc8c1");
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(37, 1, 0.1, 100);
    camera.position.set(0, 3.2, 5.3);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    host.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.target.set(0, 0.1, 0);
    controls.minDistance = 3.4;
    controls.maxDistance = 7.2;
    controlsRef.current = controls;

    const hemi = new THREE.HemisphereLight("#fff8eb", "#8f928d", 1.15);
    scene.add(hemi);

    const key = new THREE.DirectionalLight("#fff6e5", 2.05);
    key.position.set(2.8, 4.6, 3.2);
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    scene.add(key);

    const fill = new THREE.DirectionalLight("#dcece6", 0.72);
    fill.position.set(-3.4, 2.2, -2.4);
    scene.add(fill);

    const floor = new THREE.Mesh(
      new THREE.CircleGeometry(3.25, 96),
      new THREE.ShadowMaterial({ color: "#6f6d67", opacity: 0.24 })
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -0.55;
    floor.receiveShadow = true;
    scene.add(floor);

    const grid = new THREE.GridHelper(6, 24, "#78958a", "#adb5ad");
    grid.position.y = -0.535;
    grid.material.transparent = true;
    grid.material.opacity = 0.24;
    grid.visible = false;
    gridRef.current = grid;
    scene.add(grid);

    function resize() {
      const { width, height } = host.getBoundingClientRect();
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    }

    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(host);
    resize();

    let frame = 0;
    function animate() {
      frame = window.requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    }
    animate();

    return () => {
      window.cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      controls.dispose();
      renderer.dispose();
      host.removeChild(renderer.domElement);
    };
  }, []);

  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;
    if (modelRef.current) {
      scene.remove(modelRef.current);
      modelRef.current.traverse((child) => {
        if (child.geometry) child.geometry.dispose();
        if (child.material) {
          if (Array.isArray(child.material)) child.material.forEach((material) => material.dispose());
          else child.material.dispose();
        }
      });
    }
    const model = createMoldGroup(params);
    modelRef.current = model;
    scene.add(model);
  }, [params]);

  useEffect(() => {
    if (gridRef.current) gridRef.current.visible = params.grid;
  }, [params.grid]);

  return (
    <section className="preview-panel" aria-label="3D 模型预览">
      <div className="canvas-tools left-tools">
        <button className="selected" type="button" aria-label="3D 视图">
          <Box size={21} />
        </button>
        <button type="button" aria-label="重置视角" onClick={() => flash("视角已重置")}>
          <RefreshCw size={20} />
        </button>
        <button type="button" aria-label="拖拽视角">
          <Hand size={20} />
        </button>
        <button type="button" aria-label="全屏查看" onClick={() => flash("全屏预览已就绪")}>
          <Maximize size={20} />
        </button>
      </div>

      <div className="canvas-tools right-tools">
        <button type="button" onClick={() => flash("模型已居中")}>
          <Maximize size={18} />
          <span>居中</span>
        </button>
        <button
          className={params.lights ? "selected text-tool" : "text-tool"}
          type="button"
          onClick={() => update({ lights: !params.lights })}
        >
          <Sun size={18} />
          <span>光照</span>
        </button>
        <button
          className={params.grid ? "selected text-tool" : "text-tool"}
          type="button"
          onClick={() => update({ grid: !params.grid })}
        >
          <Grid3X3 size={18} />
          <span>网格</span>
        </button>
      </div>

      <div ref={hostRef} className="three-stage" />
    </section>
  );
}

function PatternRail({ params, update }) {
  return (
    <section className="pattern-rail" aria-label="花纹库">
      <div className="rail-tabs">
        {patterns.map((pattern) => (
          <button
            className={params.pattern === pattern.id ? "active" : ""}
            key={pattern.id}
            type="button"
            onClick={() => update({ pattern: pattern.id })}
          >
            {pattern.label}
          </button>
        ))}
      </div>
      <div className="pattern-strip">
        {patterns.map((pattern, index) => (
          <button
            className={params.pattern === pattern.id ? "pattern-card active" : "pattern-card"}
            key={pattern.id}
            type="button"
            onClick={() => update({ pattern: pattern.id })}
          >
            <PatternCanvas index={index} active={params.pattern === pattern.id} />
            <span>{pattern.label}</span>
          </button>
        ))}
        <button className="pattern-next" type="button" aria-label="更多花纹">
          <ChevronRight size={24} />
        </button>
      </div>
    </section>
  );
}

function PatternCanvas({ index, active }) {
  const ref = useRef(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas.getContext("2d");
    const size = canvas.width;
    ctx.clearRect(0, 0, size, size);
    ctx.fillStyle = active ? "#edf6f1" : "#f1eee8";
    ctx.fillRect(0, 0, size, size);
    ctx.translate(size / 2, size / 2);
    ctx.strokeStyle = active ? "#2f765b" : "#9b8466";
    ctx.fillStyle = active ? "rgba(47, 118, 91, .12)" : "rgba(142, 112, 76, .12)";
    ctx.lineWidth = 3;
    const petals = [16, 12, 8, 18, 10][index] ?? 12;
    for (let i = 0; i < petals; i += 1) {
      ctx.save();
      ctx.rotate((Math.PI * 2 * i) / petals);
      ctx.beginPath();
      ctx.ellipse(0, -26, 9 + (index % 2) * 3, 27 + index * 2, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.restore();
    }
    for (let ring = 0; ring < 2; ring += 1) {
      ctx.beginPath();
      ctx.arc(0, 0, 34 + ring * 10, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.setTransform(1, 0, 0, 1, 0, 0);
  }, [active, index]);

  return <canvas aria-hidden="true" className="pattern-thumb" height="96" ref={ref} width="96" />;
}

function EdgeCanvas({ type }) {
  const ref = useRef(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas.getContext("2d");
    const size = canvas.width;
    const center = size / 2;
    ctx.clearRect(0, 0, size, size);
    ctx.strokeStyle = "#2f765b";
    ctx.lineWidth = 3;
    ctx.beginPath();
    const points = 120;
    for (let i = 0; i <= points; i += 1) {
      const angle = (Math.PI * 2 * i) / points;
      const wave =
        type === "pentagon"
          ? Math.cos(angle * 5)
          : type === "rounded"
            ? Math.cos(angle * 4) * 0.35
            : type === "straight"
              ? Math.cos(angle * 36) * 0.04
              : Math.cos(angle * (type === "flower" ? 14 : 18));
      const radius = 28 * (1 - (type === "straight" ? 0.02 : 0.08) * (0.6 + 0.4 * wave));
      const x = center + Math.cos(angle) * radius;
      const y = center + Math.sin(angle) * radius;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.stroke();
  }, [type]);

  return <canvas aria-hidden="true" className="edge-drawing" height="72" ref={ref} width="72" />;
}

function SliderRow({ label, value, min, max, step, suffix, onChange }) {
  return (
    <label className="control-row">
      <span>{label}</span>
      <input
        max={max}
        min={min}
        onChange={(event) => onChange(Number(event.target.value))}
        step={step}
        type="range"
        value={value}
      />
      <output>
        {value}
        {suffix && <em>{suffix}</em>}
      </output>
    </label>
  );
}

function Inspector({ params, update, stats, exportDesign }) {
  return (
    <aside className="inspector" aria-label="参数设置">
      <section className="inspector-section open" id="shape">
        <div className="section-title">
          <h2>
            <SlidersHorizontal size={19} />
            外形设置
          </h2>
          <ChevronDown size={18} />
        </div>
        <span className="field-label">边缘样式</span>
        <div className="edge-options">
          {edgeOptions.map((option) => (
            <button
              className={params.edgeStyle === option.id ? "edge-option active" : "edge-option"}
              key={option.id}
              type="button"
              onClick={() => update({ edgeStyle: option.id })}
            >
              <EdgeCanvas type={option.id} />
              <span>{option.label}</span>
            </button>
          ))}
        </div>
        <SliderRow
          label="直径"
          max={120}
          min={60}
          onChange={(diameter) => update({ diameter })}
          step={1}
          suffix="mm"
          value={params.diameter}
        />
        <SliderRow
          label="高度"
          max={45}
          min={15}
          onChange={(height) => update({ height })}
          step={1}
          suffix="mm"
          value={params.height}
        />
        <SliderRow
          label="顶部弧度"
          max={1}
          min={0}
          onChange={(dome) => update({ dome })}
          step={0.05}
          value={params.dome}
        />
        <SliderRow
          label="花边深度"
          max={1}
          min={0.1}
          onChange={(scallopDepth) => update({ scallopDepth })}
          step={0.05}
          value={params.scallopDepth}
        />
        <SliderRow
          label="花边齿数"
          max={28}
          min={8}
          onChange={(scallopCount) => update({ scallopCount })}
          step={1}
          value={params.scallopCount}
        />
      </section>

      <section className="inspector-section" id="pattern">
        <div className="section-title">
          <h2>
            <Image size={19} />
            花纹设置
          </h2>
          <ChevronDown size={18} />
        </div>
        <div className="pattern-actions">
          <span className="mini-preview" />
          <button type="button">
            <Link size={17} />
            更换花纹
          </button>
          <button type="button">
            <Sparkles size={17} />
            镜像花纹
          </button>
        </div>
        <SliderRow
          label="深度"
          max={2}
          min={0.2}
          onChange={(patternDepth) => update({ patternDepth })}
          step={0.1}
          suffix="mm"
          value={params.patternDepth}
        />
        <div className="segmented-row">
          <span>细节精度</span>
          <div className="segmented">
            {["low", "medium", "high"].map((quality) => (
              <button
                className={params.detailQuality === quality ? "selected" : ""}
                key={quality}
                type="button"
                onClick={() => update({ detailQuality: quality })}
              >
                {{ low: "低", medium: "中", high: "高" }[quality]}
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="inspector-section" id="text">
        <div className="section-title">
          <h2>
            <Type size={19} />
            刻字设置
          </h2>
          <ChevronDown size={18} />
        </div>
        <input
          className="text-input"
          onChange={(event) => update({ text: event.target.value })}
          placeholder="输入文字（支持中文、英文、数字）"
          value={params.text}
        />
        <label className="select-row">
          <span>字体</span>
          <select value={params.font} onChange={(event) => update({ font: event.target.value })}>
            <option>思源黑体</option>
            <option>霞鹜文楷</option>
            <option>系统无衬线</option>
          </select>
        </label>
        <SliderRow
          label="深度"
          max={1.6}
          min={0.1}
          onChange={(textDepth) => update({ textDepth })}
          step={0.1}
          suffix="mm"
          value={params.textDepth}
        />
      </section>

      <section className="inspector-section compact" id="material">
        <div className="section-title">
          <h2>
            <Palette size={19} />
            颜色与材质
          </h2>
          <ChevronDown size={18} />
        </div>
        <div className="material-row">
          {[
            ["cream", "奶油白（推荐 PLA）"],
            ["resin", "树脂绿"],
            ["graphite", "石墨灰"],
          ].map(([id, label]) => (
            <button
              className={params.material === id ? `swatch ${id} active` : `swatch ${id}`}
              key={id}
              type="button"
              onClick={() => update({ material: id })}
            >
              <span />
              {label}
            </button>
          ))}
        </div>
      </section>

      <section className="inspector-section print-block" id="print">
        <div className="section-title">
          <h2>
            <Layers size={19} />
            打印分析
          </h2>
          <span className={stats.printable ? "print-status ready" : "print-status warn"}>
            {stats.printable ? "可打印" : "需调整"}
          </span>
        </div>
        <div className="print-grid">
          <span>壁厚</span>
          <strong>{stats.wall}mm</strong>
          <span>材料</span>
          <strong>PLA</strong>
          <span>估算重量</span>
          <strong>{stats.grams}g</strong>
          <span>预计时间</span>
          <strong>{stats.time}</strong>
        </div>
      </section>

      <div className="drawer-actions">
        <button className="export-primary" type="button" onClick={() => exportDesign("stl")}>
          <Download size={20} />
          导出 STL
        </button>
        <button className="export-secondary" type="button" onClick={() => exportDesign("glb")}>
          <Box size={20} />
          导出 GLB
        </button>
      </div>
    </aside>
  );
}

function Metrics({ stats, params, message }) {
  const items = [
    { icon: Ruler, label: "尺寸", value: `${params.diameter}mm` },
    { icon: SlidersHorizontal, label: "高度", value: `${params.height}mm` },
    { icon: Layers, label: "材料", value: "PLA" },
    { icon: Sparkles, label: "预计用料", value: `${stats.grams}g` },
    { icon: Clock, label: "预计时间", value: stats.time },
  ];

  return (
    <footer className="metrics-bar">
      <div className="save-status">
        <CheckCircle2 size={22} />
        <div>
          <strong>{message}</strong>
          <span>自动保存：刚刚</span>
        </div>
      </div>
      <div className="metrics">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <div className="metric" key={item.label}>
              <Icon size={24} />
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </div>
          );
        })}
      </div>
    </footer>
  );
}

function downloadBlob(blob, fileName) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(link.href), 500);
}

export function App() {
  const [params, setParams] = useState(defaultParams);
  const [message, flash] = useDebouncedMessage();
  const stats = useMemo(() => calculatePrintStats(params), [params]);

  function update(nextParams) {
    setParams((current) => ({ ...current, ...nextParams }));
  }

  function exportDesign(type) {
    const exportParams = { ...params, view: "mold" };
    const group = createMoldGroup(exportParams);
    group.updateMatrixWorld(true);

    if (type === "stl") {
      const stl = new STLExporter().parse(group, { binary: false });
      downloadBlob(new Blob([stl], { type: "model/stl" }), "mooncake-mold-material-studio.stl");
      flash("STL 已导出");
      return;
    }

    new GLTFExporter().parse(
      group,
      (result) => {
        const payload = result instanceof ArrayBuffer ? result : JSON.stringify(result, null, 2);
        const mime = result instanceof ArrayBuffer ? "model/gltf-binary" : "model/gltf+json";
        downloadBlob(new Blob([payload], { type: mime }), "mooncake-mold-material-studio.glb");
        flash("GLB 已导出");
      },
      (error) => {
        flash("GLB 导出失败，请重试");
        console.error(error);
      },
      { binary: true }
    );
  }

  return (
    <main className="app-shell">
      <Header exportDesign={exportDesign} params={params} update={update} />

      <div className="workspace">
        <div className="preview-column">
          <MoldViewport flash={flash} params={params} update={update} />
          <PatternRail params={params} update={update} />
          <Metrics message={message} params={params} stats={stats} />
        </div>
        <Inspector exportDesign={exportDesign} params={params} stats={stats} update={update} />
      </div>
    </main>
  );
}
