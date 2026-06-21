const DIAGNOSTIC_TERMS = [
  'diagnosis',
  'diagnose',
  'depression',
  'mental illness',
  'suicide',
  'ai therapist',
  'medical burnout detector',
];

function clamp(value, min, max) {
  const n = Number(value);
  if (!Number.isFinite(n)) return min;
  return Math.max(min, Math.min(max, n));
}

function mean(values) {
  const nums = values.map(Number).filter(Number.isFinite);
  if (!nums.length) return null;
  return nums.reduce((sum, value) => sum + value, 0) / nums.length;
}

function slope(values) {
  const nums = values.map(Number).filter(Number.isFinite);
  const n = nums.length;
  if (n < 2) return 0;
  const mx = (n - 1) / 2;
  const my = mean(nums);
  let num = 0;
  let den = 0;
  for (let i = 0; i < n; i += 1) {
    num += (i - mx) * (nums[i] - my);
    den += (i - mx) ** 2;
  }
  return den ? num / den : 0;
}

function normalizeEntry(entry) {
  if (!entry || typeof entry !== 'object') return {};
  return entry.signals && typeof entry.signals === 'object'
    ? { ...entry.signals, risk: entry.risk, tracker: entry.tracker || entry.trackerToday }
    : entry;
}

function valueFrom(entry, key, fallback) {
  const normalized = normalizeEntry(entry);
  const value = normalized[key];
  return Number.isFinite(Number(value)) ? Number(value) : fallback;
}

function contextValue(context, key) {
  if (!context || typeof context !== 'object') return undefined;
  return context[key];
}

function sanitizeExplanation(text) {
  let out = String(text || '');
  for (const term of DIAGNOSTIC_TERMS) {
    out = out.replace(new RegExp(term, 'ig'), 'wellbeing pattern');
  }
  return out;
}

function calculateAdaptiveRisk(inputs = {}, history = [], meta = {}) {
  const context = meta.trackerToday || meta.context || {};
  const hist = Array.isArray(history) ? history.map(normalizeEntry).slice(0, 42) : [];

  const stress = clamp(inputs.stress ?? 5, 1, 10);
  const energy = clamp(inputs.energy ?? inputs.mood ?? 5, 1, 10);
  const sleepQuality = clamp(inputs.sleepQuality ?? inputs.sleep_quality ?? inputs.sleep ?? 7, 1, 10);
  const overwhelm = clamp(inputs.overwhelm ?? inputs.deadline_pressure ?? 5, 1, 10);
  const pressure = clamp(inputs.studyWorkPressure ?? inputs.work_pressure ?? inputs.deadline_pressure ?? 5, 1, 10);
  const recovery = clamp(inputs.recoveryTime ?? inputs.recovery ?? inputs.recovery_time ?? 5, 1, 10);
  const motivation = clamp(inputs.motivation ?? 5, 1, 10);
  const focus = clamp(inputs.focus ?? 5, 1, 10);
  const socialBattery = clamp(inputs.socialBattery ?? inputs.social_battery ?? inputs.peer_support ?? 5, 1, 10);

  const contributors = [];
  const protectiveFactors = [];
  const component = {
    stress: ((stress - 1) / 9) * 20,
    energy: ((10 - energy) / 9) * 13,
    sleep: ((10 - sleepQuality) / 9) * 13,
    overwhelm: ((overwhelm - 1) / 9) * 15,
    pressure: ((pressure - 1) / 9) * 12,
    recovery: ((10 - recovery) / 9) * 10,
    motivation: ((10 - motivation) / 9) * 7,
    focus: ((10 - focus) / 9) * 6,
    socialBattery: ((10 - socialBattery) / 9) * 5,
  };
  let coreScore = Object.values(component).reduce((sum, value) => sum + value, 0);

  if (stress >= 8) contributors.push('stress level is high');
  if (energy <= 4) contributors.push('energy is low');
  if (sleepQuality <= 4) contributors.push('sleep quality is low');
  if (overwhelm >= 8) contributors.push('overwhelm is high');
  if (pressure >= 8) contributors.push('study/work pressure is high');
  if (recovery <= 3) contributors.push('recovery time is low');
  if (socialBattery <= 3) contributors.push('social battery is low');

  let contextModifier = 0;
  const social = contextValue(context, 'socialInteractionQuality') || contextValue(context, 'socialConnection');
  if (social === 'Supportive') {
    contextModifier -= 4;
    protectiveFactors.push('supportive social connection');
  } else if (social === 'Draining') {
    contextModifier += 4;
    contributors.push('social interaction felt draining');
  } else if (social === 'Isolated') {
    contextModifier += 5;
    contributors.push('isolation may be adding strain');
  }

  const substance = contextValue(context, 'substanceUseContext') || contextValue(context, 'alcohol');
  if (substance === 'Connected') {
    contextModifier -= 1;
    protectiveFactors.push('substance use was in a supportive social context');
  } else if (substance === 'To cope') {
    contextModifier += 5;
    contributors.push('substance use was coping-related');
  } else if (substance === 'Affected sleep') {
    contextModifier += 6;
    contributors.push('substance use may have affected sleep or mood');
  }

  const screen = contextValue(context, 'screenTimeContext') || contextValue(context, 'screenTime');
  if (screen === 'Connecting' || screen === 'Relaxing') {
    contextModifier -= 1;
  } else if (screen === 'Avoidance') {
    contextModifier += 4;
    contributors.push('screen time may be avoidance');
  } else if (screen === 'Late-night') {
    contextModifier += 5;
    contributors.push('late-night screen time may be affecting recovery');
  }

  const movement = contextValue(context, 'movement') || contextValue(context, 'sport');
  if (movement === 'Light' || movement === 'Active') {
    contextModifier -= 2;
    protectiveFactors.push('some movement');
  } else if (movement === 'None') {
    contextModifier += 2;
  } else if (movement === 'Excessive') {
    contextModifier += 2;
    contributors.push('movement may be stress-driven rather than restorative');
  }

  if (contextValue(context, 'recoveryTime') === 'Real rest') {
    contextModifier -= 4;
    protectiveFactors.push('real recovery time');
  } else if (contextValue(context, 'recoveryTime') === 'None') {
    contextModifier += 5;
    contributors.push('no real recovery time');
  }

  contextModifier = clamp(contextModifier, -15, 15);

  let trendModifier = 0;
  if (hist.length >= 3) {
    const recent = hist.slice(0, 7);
    const highStressDays = recent.filter(day => valueFrom(day, 'stress', 5) >= 8).length;
    if (highStressDays >= 3) {
      trendModifier += 9;
      contributors.push('repeated high-stress days');
    }

    const sleepSlope = slope(recent.map(day => valueFrom(day, 'sleepQuality', valueFrom(day, 'sleep', 7))).reverse());
    if (sleepSlope < -0.25) {
      trendModifier += 5;
      contributors.push('sleep has been worsening');
    }

    const socialSlope = slope(recent.map(day => valueFrom(day, 'socialBattery', valueFrom(day, 'peer_support', 5))).reverse());
    if (socialSlope < -0.25) {
      trendModifier += 4;
      contributors.push('social battery has been decreasing');
    }

    const recoveryLowDays = recent.filter(day => valueFrom(day, 'recoveryTime', valueFrom(day, 'recovery', 5)) <= 3).length;
    if (recoveryLowDays >= 3) {
      trendModifier += 7;
      contributors.push('recovery has been low for several days');
    }

    const overwhelmSlope = slope(recent.map(day => valueFrom(day, 'overwhelm', valueFrom(day, 'deadline_pressure', 5))).reverse());
    if (overwhelmSlope > 0.25) {
      trendModifier += 5;
      contributors.push('overwhelm has been rising');
    }
  }

  const previousRisk = hist.length && Number.isFinite(Number(hist[0].risk))
    ? Number(hist[0].risk) * (Number(hist[0].risk) <= 1 ? 100 : 1)
    : 0;
  let recoveryDrag = 0;
  if (previousRisk >= 75 && coreScore + contextModifier < 45) {
    recoveryDrag = Math.min(18, (previousRisk - 55) * 0.35);
    contributors.push('risk decreases gradually after a high-risk day');
  }

  let baselineAdjustment = 0;
  let baselineStatus = 'learning';
  if (hist.length >= 14) {
    baselineStatus = hist.length >= 28 ? 'personalized' : 'warming_up';
    const baseline = {
      stress: mean(hist.map(day => valueFrom(day, 'stress', NaN))),
      sleepQuality: mean(hist.map(day => valueFrom(day, 'sleepQuality', valueFrom(day, 'sleep', NaN)))),
      recoveryTime: mean(hist.map(day => valueFrom(day, 'recoveryTime', valueFrom(day, 'recovery', NaN)))),
      socialBattery: mean(hist.map(day => valueFrom(day, 'socialBattery', valueFrom(day, 'peer_support', NaN)))),
    };
    if (baseline.stress != null && stress >= baseline.stress + 1.5) baselineAdjustment += 5;
    if (baseline.sleepQuality != null && sleepQuality <= baseline.sleepQuality - 1.3) baselineAdjustment += 5;
    if (baseline.recoveryTime != null && recovery <= baseline.recoveryTime - 1.3) baselineAdjustment += 4;
    if (baseline.socialBattery != null && socialBattery <= baseline.socialBattery - 1.3) baselineAdjustment += 3;
    if (baseline.stress != null && stress <= baseline.stress - 1.5) baselineAdjustment -= 3;
    if (baseline.sleepQuality != null && sleepQuality >= baseline.sleepQuality + 1.3) baselineAdjustment -= 3;
  }

  const rawScore = coreScore + contextModifier + trendModifier + recoveryDrag + baselineAdjustment;
  const scorePct = Math.round(clamp(rawScore, 0, 100));
  const riskLevel = scorePct <= 30 ? 'Low'
    : scorePct <= 55 ? 'Moderate'
      : scorePct <= 75 ? 'High'
        : 'Very high';

  const reason = contributors[0] || protectiveFactors[0] || 'your current pattern is relatively steady';
  const explanation = sanitizeExplanation(
    `Your stress risk is ${riskLevel.toLowerCase()} mainly because ${reason}.`
  );

  return {
    scorePct,
    scoreProb: scorePct / 100,
    riskLevel,
    components: {
      coreScore: Math.round(coreScore),
      contextModifier: Math.round(contextModifier),
      trendModifier: Math.round(trendModifier),
      recoveryDrag: Math.round(recoveryDrag),
      baselineAdjustment: Math.round(baselineAdjustment),
    },
    baselineStatus,
    contributors: [...new Set(contributors)].slice(0, 6),
    protectiveFactors: [...new Set(protectiveFactors)].slice(0, 6),
    explanation,
  };
}

module.exports = {
  DIAGNOSTIC_TERMS,
  calculateAdaptiveRisk,
  sanitizeExplanation,
};
