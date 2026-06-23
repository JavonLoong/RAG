import * as THREE from "three";

const MATERIALS = {
  cream: { color: "#f1dfbd", roughness: 0.72, metalness: 0.02 },
  resin: { color: "#d8ece4", roughness: 0.58, metalness: 0.05 },
  graphite: { color: "#cfd4d1", roughness: 0.46, metalness: 0.08 },
};

function scallopedShape(radius, scallopDepth, scallopCount, style) {
  const shape = new THREE.Shape();
  const segments = 256;
  const styleFactor = {
    wave: 0.058,
    straight: 0.012,
    flower: 0.045,
    pentagon: 0.03,
    rounded: 0.018,
  }[style] ?? 0.04;

  for (let index = 0; index <= segments; index += 1) {
    const angle = (index / segments) * Math.PI * 2;
    let wave = 0;

    if (style === "pentagon") {
      wave = Math.cos(angle * 5);
    } else if (style === "rounded") {
      wave = Math.cos(angle * 4) * 0.35;
    } else if (style === "straight") {
      wave = Math.cos(angle * 28) * 0.08;
    } else {
      wave = Math.cos(angle * scallopCount);
    }

    const localRadius = radius * (1 - styleFactor * scallopDepth * (0.55 + 0.45 * wave));
    const x = Math.cos(angle) * localRadius;
    const y = Math.sin(angle) * localRadius;
    if (index === 0) shape.moveTo(x, y);
    else shape.lineTo(x, y);
  }

  return shape;
}

function makePetalTexture(params) {
  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = 1024;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.translate(512, 512);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";

  const lineColor = params.view === "mold" ? "rgba(45, 82, 68, .74)" : "rgba(156, 109, 50, .54)";
  const fillColor = params.view === "mold" ? "rgba(45, 118, 91, .12)" : "rgba(188, 132, 60, .16)";
  ctx.strokeStyle = lineColor;
  ctx.fillStyle = fillColor;
  ctx.lineWidth = 9;

  const patternMap = {
    lotus: 16,
    classic: 12,
    geometric: 10,
    festival: 18,
    custom: 14,
  };
  const petals = patternMap[params.pattern] ?? 16;

  for (let i = 0; i < petals; i += 1) {
    ctx.save();
    ctx.rotate((Math.PI * 2 * i) / petals);
    ctx.beginPath();
    ctx.ellipse(0, -232, 46, 166, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.restore();
  }

  ctx.strokeStyle = params.view === "mold" ? "rgba(45, 82, 68, .58)" : "rgba(142, 97, 42, .48)";
  ctx.lineWidth = 7;
  for (let ring = 0; ring < 3; ring += 1) {
    ctx.beginPath();
    ctx.arc(0, 0, 260 + ring * 38, 0, Math.PI * 2);
    ctx.stroke();
  }

  ctx.beginPath();
  ctx.arc(0, 0, 108, 0, Math.PI * 2);
  ctx.fillStyle = params.view === "mold" ? "rgba(45, 118, 91, .10)" : "rgba(255, 255, 255, .16)";
  ctx.fill();
  ctx.stroke();

  if (params.text.trim()) {
    ctx.fillStyle = params.view === "mold" ? "rgba(31, 69, 58, .76)" : "rgba(115, 78, 35, .64)";
    ctx.font = "700 70px 'Noto Sans SC', sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(params.text.trim().slice(0, 6), 0, 5);
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 8;
  return texture;
}

function makeSideGrooves(radius, height, scallopCount, view) {
  const group = new THREE.Group();
  const grooveMaterial = new THREE.MeshStandardMaterial({
    color: view === "mold" ? "#b9d0c5" : "#e1bd79",
    roughness: 0.75,
    metalness: 0.02,
    transparent: true,
    opacity: view === "mold" ? 0.5 : 0.38,
  });

  for (let i = 0; i < scallopCount; i += 1) {
    const angle = (Math.PI * 2 * i) / scallopCount;
    const groove = new THREE.Mesh(
      new THREE.BoxGeometry(0.018, height * 0.62, 0.18),
      grooveMaterial
    );
    groove.position.set(Math.cos(angle) * radius * 0.965, 0, Math.sin(angle) * radius * 0.965);
    groove.rotation.y = -angle;
    group.add(groove);
  }

  return group;
}

function makeReliefPetals(radius, topY, params) {
  const group = new THREE.Group();
  const petalMaterial = new THREE.MeshBasicMaterial({
    color: params.view === "mold" ? "#b9d8cb" : "#dfbe7f",
    transparent: true,
    opacity: params.view === "mold" ? 0.68 : 0.46,
    side: THREE.DoubleSide,
    depthTest: false,
    depthWrite: false,
  });
  const veinMaterial = new THREE.MeshBasicMaterial({
    color: params.view === "mold" ? "#8bb7a5" : "#c99856",
    transparent: true,
    opacity: 0.64,
    side: THREE.DoubleSide,
    depthTest: false,
    depthWrite: false,
  });
  const patternMap = {
    lotus: 16,
    classic: 12,
    geometric: 10,
    festival: 18,
    custom: 14,
  };
  const petals = patternMap[params.pattern] ?? 16;
  const petalGeometry = new THREE.CircleGeometry(1, 40);
  const veinGeometry = new THREE.PlaneGeometry(0.012, radius * 0.32, 1, 1);

  for (let i = 0; i < petals; i += 1) {
    const angle = (Math.PI * 2 * i) / petals;
    const petal = new THREE.Mesh(petalGeometry, petalMaterial);
    petal.scale.set(radius * 0.065, radius * 0.27, 1);
    petal.rotation.x = -Math.PI / 2;
    petal.rotation.z = angle;
    petal.position.set(Math.sin(angle) * radius * 0.36, topY + 0.029, Math.cos(angle) * radius * 0.36);
    petal.renderOrder = 5;
    group.add(petal);

    const vein = new THREE.Mesh(veinGeometry, veinMaterial);
    vein.rotation.x = -Math.PI / 2;
    vein.rotation.z = angle;
    vein.position.set(Math.sin(angle) * radius * 0.36, topY + 0.032, Math.cos(angle) * radius * 0.36);
    vein.renderOrder = 6;
    group.add(vein);
  }

  const centerRing = new THREE.Mesh(
    new THREE.TorusGeometry(radius * 0.18, 0.008, 8, 80),
    veinMaterial
  );
  centerRing.rotation.x = -Math.PI / 2;
  centerRing.position.y = topY + 0.035;
  centerRing.renderOrder = 7;
  group.add(centerRing);
  return group;
}

export function createMoldGroup(params) {
  const group = new THREE.Group();
  const radius = params.diameter / 50;
  const height = params.height / 42;
  const materialSpec = MATERIALS[params.material] ?? MATERIALS.cream;
  const bodyColor = params.view === "mold" ? "#dbe9e2" : materialSpec.color;

  const shape = scallopedShape(radius, params.scallopDepth, params.scallopCount, params.edgeStyle);
  const bodyGeometry = new THREE.ExtrudeGeometry(shape, {
    depth: height,
    bevelEnabled: true,
    bevelSize: 0.055,
    bevelThickness: 0.09,
    bevelSegments: 8,
    curveSegments: 18,
    steps: 1,
  });
  bodyGeometry.center();
  bodyGeometry.rotateX(-Math.PI / 2);

  const body = new THREE.Mesh(
    bodyGeometry,
    new THREE.MeshStandardMaterial({
      color: bodyColor,
      roughness: materialSpec.roughness,
      metalness: materialSpec.metalness,
      envMapIntensity: 0.62,
    })
  );
  body.castShadow = true;
  body.receiveShadow = true;
  group.add(body);
  group.add(makeSideGrooves(radius, height, params.scallopCount, params.view));

  const topY = height / 2 + 0.012;
  const patternTexture = makePetalTexture(params);
  const patternPlane = new THREE.Mesh(
    new THREE.CircleGeometry(radius * 0.82, 160),
    new THREE.MeshStandardMaterial({
      map: patternTexture,
      transparent: true,
      roughness: 0.64,
      metalness: 0.01,
      polygonOffset: true,
      polygonOffsetFactor: -1,
    })
  );
  patternPlane.rotation.x = -Math.PI / 2;
  patternPlane.position.y = topY + 0.045 + params.patternDepth * 0.002;
  patternPlane.renderOrder = 3;
  group.add(patternPlane);
  group.add(makeReliefPetals(radius, topY, params));

  const center = new THREE.Mesh(
    new THREE.CylinderGeometry(radius * 0.18, radius * 0.22, 0.07 + params.dome * 0.06, 64),
    new THREE.MeshStandardMaterial({
      color: params.view === "mold" ? "#c7ddd2" : "#f4e5c9",
      roughness: 0.66,
      metalness: 0.02,
    })
  );
  center.position.y = topY + 0.035;
  center.castShadow = true;
  group.add(center);

  const rimMaterial = new THREE.MeshStandardMaterial({
    color: params.view === "mold" ? "#a9c9ba" : "#d8b471",
    roughness: 0.7,
    metalness: 0.02,
  });
  const rim = new THREE.Mesh(new THREE.TorusGeometry(radius * 0.86, 0.018, 10, 160), rimMaterial);
  rim.rotation.x = -Math.PI / 2;
  rim.position.y = topY + 0.018;
  group.add(rim);

  group.rotation.y = -0.28;
  group.rotation.x = 0.03;
  return group;
}

export function calculatePrintStats(params) {
  const diameterFactor = params.diameter / 85;
  const heightFactor = params.height / 25;
  const patternFactor = 1 + params.patternDepth * 0.08 + params.scallopDepth * 0.12;
  const grams = Math.round(327 * diameterFactor * diameterFactor * heightFactor * patternFactor) / 10;
  const minutes = Math.round(112 * diameterFactor * heightFactor * patternFactor + params.scallopCount * 1.5);
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;

  return {
    grams,
    time: `${hours} h ${mins} m`,
    printable: params.height >= 18 && params.patternDepth <= 1.8 && params.diameter <= 110,
    wall: Math.max(1.2, Math.round((params.height / 18) * 10) / 10),
  };
}
