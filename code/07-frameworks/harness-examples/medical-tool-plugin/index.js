/**
 * DeepSeek Harness Host 插件示例：医疗教学工具
 * 
 * 这个插件演示了如何为 DSH Agent 添加自定义工具。
 * 工具通过 ctx.tools.register() 注册，Agent 可以在对话中调用它们。
 * 
 * 关键点：
 * 1. 使用 export function apply(ctx, config) 形式导出
 * 2. 在 ctx.effect() 中注册工具，返回清理函数
 * 3. 工具定义包含 name、description、parameters（JSON Schema）
 * 4. execute 函数接收参数，返回结果给 Agent
 */

export function apply(ctx, config) {
  // 使用 ctx.effect 注册资源，插件卸载时自动清理
  return ctx.effect(() => {
    // 注册第一个工具：生成模拟临床病例
    const unregisterCaseGen = ctx.tools.register({
      name: 'medical_case_generator',
      description: `生成一个模拟的临床教学病例。用于医学教育场景，不包含真实患者信息。

参数说明：
- topic: 疾病主题，如"社区获得性肺炎"、"急性胸痛"
- level: 学习者层级，如"R1"、"R2"、"主治医师"
- complexity: 复杂度，"basic"（基础）、"intermediate"（中等）、"advanced"（高级）

返回：结构化的病例文本，包含主诉、现病史、既往史、查体、辅助检查。`,
      parameters: {
        type: 'object',
        properties: {
          topic: {
            type: 'string',
            description: '疾病主题，如"社区获得性肺炎"'
          },
          level: {
            type: 'string',
            description: '学习者层级',
            enum: ['R1', 'R2', 'R3', '主治医师', '副主任医师']
          },
          complexity: {
            type: 'string',
            description: '病例复杂度',
            enum: ['basic', 'intermediate', 'advanced'],
            default: 'intermediate'
          }
        },
        required: ['topic', 'level']
      },
      async execute(args) {
        // 实际项目中这里可以调用 LLM 或查询数据库
        // 这里返回一个模板化的示例
        const { topic, level, complexity = 'intermediate' } = args;
        
        const cases = {
          basic: generateBasicCase(topic, level),
          intermediate: generateIntermediateCase(topic, level),
          advanced: generateAdvancedCase(topic, level)
        };
        
        return {
          content: [{
            type: 'text',
            text: cases[complexity] || cases.intermediate
          }]
        };
      }
    });

    // 注册第二个工具：验证教学计划
    const unregisterValidator = ctx.tools.register({
      name: 'teaching_plan_validator',
      description: `验证一份教学计划是否符合医学教育规范。

检查项：
1. 教学目标是否使用 Bloom 分类法（可观察、可评价的行为动词）
2. 时间分配是否合理（总时长、各环节占比）
3. 评价方式是否与目标对齐
4. 是否包含形成性评价和总结性评价

参数：
- plan: 教学计划文本（Markdown 格式）

返回：验证报告，包含通过/不通过、问题列表、改进建议。`,
      parameters: {
        type: 'object',
        properties: {
          plan: {
            type: 'string',
            description: '教学计划文本，Markdown 格式'
          }
        },
        required: ['plan']
      },
      async execute(args) {
        const { plan } = args;
        const issues = [];
        const suggestions = [];

        // 简单的规则检查（实际项目可以用 LLM 做更智能的验证）
        
        // 检查 1：是否有明确的教学目标
        if (!plan.includes('目标') && !plan.includes('Objective')) {
          issues.push('缺少明确的教学目标部分');
          suggestions.push('添加"教学目标"章节，使用 Bloom 分类法描述可观察的行为');
        }

        // 检查 2：是否使用了模糊动词
        const vagueVerbs = ['了解', '掌握', '熟悉', '知道'];
        const foundVague = vagueVerbs.filter(v => plan.includes(v));
        if (foundVague.length > 0) {
          issues.push(`使用了模糊动词：${foundVague.join('、')}，这些词无法直接观察和评价`);
          suggestions.push('替换为可观察的行为动词，如"能列出"、"能解释"、"能演示"');
        }

        // 检查 3：是否有时间分配
        if (!plan.match(/\d+\s*分钟|\d+\s*min/i)) {
          issues.push('缺少具体的时间分配');
          suggestions.push('为每个教学环节标注预计时长');
        }

        // 检查 4：是否有评价方式
        if (!plan.includes('评价') && !plan.includes('评估') && !plan.includes('考核')) {
          issues.push('缺少评价方式说明');
          suggestions.push('添加评价方式，说明如何判断学员是否达到教学目标');
        }

        const passed = issues.length === 0;
        
        return {
          content: [{
            type: 'text',
            text: `## 教学计划验证报告

**验证结果**：${passed ? '✅ 通过' : '⚠️ 需要修改'}

### 发现的问题（${issues.length} 项）
${issues.length > 0 ? issues.map((issue, i) => `${i + 1}. ${issue}`).join('\n') : '无'}

### 改进建议
${suggestions.length > 0 ? suggestions.map((s, i) => `${i + 1}. ${s}`).join('\n') : '当前计划符合基本规范'}

### 检查清单
- [${plan.includes('目标') || plan.includes('Objective') ? 'x' : ' '}] 教学目标明确
- [${foundVague.length === 0 ? 'x' : ' '}] 使用可观察的行为动词
- [${plan.match(/\d+\s*分钟|\d+\s*min/i) ? 'x' : ' '}] 时间分配具体
- [${plan.includes('评价') || plan.includes('评估') || plan.includes('考核') ? 'x' : ' '}] 评价方式明确
`
          }]
        };
      }
    });

    // 返回清理函数：插件卸载时取消注册工具
    return () => {
      unregisterCaseGen();
      unregisterValidator();
    };
  });
}

// 辅助函数：生成不同复杂度的病例
function generateBasicCase(topic, level) {
  return `# 基础教学病例：${topic}

**适用对象**：${level}

## 主诉
患者因"${getChiefComplaint(topic)}"就诊。

## 现病史
患者于${getOnsetTime(topic)}前出现症状，逐渐加重。

## 既往史
否认特殊病史。

## 体格检查
生命体征平稳，专科查体见${getPhysicalFindings(topic, 'basic')}。

## 辅助检查
${getLabResults(topic, 'basic')}

## 教学要点
1. 识别典型临床表现
2. 掌握基本诊断思路
3. 了解一线治疗方案

---
*本病例为模拟病例，仅用于教学目的。*`;
}

function generateIntermediateCase(topic, level) {
  return `# 中等复杂度教学病例：${topic}

**适用对象**：${level}

## 主诉
${getChiefComplaint(topic)}，伴${getAssociatedSymptoms(topic)}。

## 现病史
患者于${getOnsetTime(topic)}前开始出现症状。初期表现为${getInitialSymptoms(topic)}，自行处理后未缓解。近${getRecentDays(topic)}天症状加重，出现${getWorseningSymptoms(topic)}。

## 既往史
${getPastHistory(topic, 'intermediate')}

## 体格检查
T ${getVitalSigns(topic).temp}℃，P ${getVitalSigns(topic).pulse}次/分，R ${getVitalSigns(topic).resp}次/分，BP ${getVitalSigns(topic).bp}mmHg。
${getPhysicalFindings(topic, 'intermediate')}

## 辅助检查
${getLabResults(topic, 'intermediate')}

## 教学提示
1. 本病例故意保留部分信息缺口，请学习者主动提问
2. 注意鉴别诊断的思考过程
3. 关注病情严重程度分层

## 讨论问题
1. 该患者的初步诊断是什么？依据有哪些？
2. 需要补充哪些检查来明确诊断？
3. 初始治疗方案如何选择？

---
*本病例为模拟病例，仅用于教学目的。*`;
}

function generateAdvancedCase(topic, level) {
  return `# 高级教学病例：${topic}（复杂/不典型表现）

**适用对象**：${level}

## 主诉
${getChiefComplaint(topic)}，病程迁延，多次就诊未明确诊断。

## 现病史
患者于${getOnsetTime(topic)}前起病，初期表现不典型。曾在外院按"${getMisdiagnosis(topic)}"治疗，效果不佳。近${getRecentDays(topic)}天出现${getComplications(topic)}，病情复杂化。

## 既往史
${getPastHistory(topic, 'advanced')}

## 体格检查
${getVitalSignsAdvanced(topic)}
${getPhysicalFindings(topic, 'advanced')}

## 辅助检查
${getLabResults(topic, 'advanced')}

## 影像学检查
${getImagingResults(topic)}

## 诊疗经过
1. 外院诊治经过：${getExternalTreatment(topic)}
2. 入院后检查：${getInpatientWorkup(topic)}
3. 多学科会诊意见：${getMDTOpinion(topic)}

## 教学难点
1. 不典型表现的识别与鉴别
2. 多系统受累时的诊断思路
3. 治疗反应不佳时的策略调整
4. 医患沟通与知情同意

## 深入讨论
1. 如果初始诊断错误，可能的原因是什么？
2. 如何避免类似的诊断延误？
3. 该病例对临床实践有什么启示？

---
*本病例为模拟病例，基于真实临床场景改编，仅用于教学目的。*`;
}

// 辅助数据函数
function getChiefComplaint(topic) {
  const complaints = {
    '社区获得性肺炎': '发热、咳嗽、咳痰',
    '急性胸痛': '突发胸痛',
    '急性腹痛': '突发腹痛',
    '头痛': '反复头痛',
    'default': '不适'
  };
  return complaints[topic] || complaints.default;
}

function getAssociatedSymptoms(topic) {
  const symptoms = {
    '社区获得性肺炎': '气促、乏力',
    '急性胸痛': '胸闷、出汗',
    '急性腹痛': '恶心、呕吐',
    'default': '乏力、食欲减退'
  };
  return symptoms[topic] || symptoms.default;
}

function getOnsetTime(topic) {
  return '3-5 天';
}

function getInitialSymptoms(topic) {
  return '轻微不适';
}

function getRecentDays(topic) {
  return '2';
}

function getWorseningSymptoms(topic) {
  return '症状明显加重';
}

function getMisdiagnosis(topic) {
  return '普通感冒';
}

function getComplications(topic) {
  return '新的并发症表现';
}

function getPastHistory(topic, complexity) {
  if (complexity === 'advanced') {
    return '高血压病史 10 年，糖尿病病史 5 年，长期吸烟史。';
  }
  return '否认特殊病史。';
}

function getVitalSigns(topic) {
  return { temp: 38.5, pulse: 98, resp: 22, bp: '120/80' };
}

function getVitalSignsAdvanced(topic) {
  return `T 39.2℃，P 112次/分，R 28次/分，BP 95/60mmHg，SpO₂ 92%（未吸氧）。`;
}

function getPhysicalFindings(topic, complexity) {
  if (complexity === 'basic') {
    return '阳性体征';
  } else if (complexity === 'intermediate') {
    return '专科查体可见明确阳性体征，需结合病史综合分析。';
  } else {
    return '多系统查体异常，体征复杂，需仔细鉴别。';
  }
}

function getLabResults(topic, complexity) {
  if (complexity === 'basic') {
    return '血常规、生化基本正常。';
  } else if (complexity === 'intermediate') {
    return '血常规示白细胞升高，炎症指标增高。';
  } else {
    return '多项检查异常，包括血常规、生化、凝血功能、炎症指标等，需综合判读。';
  }
}

function getImagingResults(topic) {
  return '影像学检查显示复杂改变，需结合临床综合判断。';
}

function getExternalTreatment(topic) {
  return '按常见病治疗，效果不佳。';
}

function getInpatientWorkup(topic) {
  return '完善相关检查，明确诊断。';
}

function getMDTOpinion(topic) {
  return '多学科讨论后制定个体化治疗方案。';
}
