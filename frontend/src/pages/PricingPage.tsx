import React, { useEffect, useState } from 'react';

interface PlanFeatures {
  plan: string;
  features: Record<string, boolean>;
  quota: Record<string, number | boolean>;
}

const FEATURE_LABELS: Record<string, string> = {
  distributed_execution: '分布式执行引擎',
  custom_plugins: '自定义故障插件',
  cicd_integration: 'CI/CD 集成',
  advanced_analytics: '高级分析与对比',
  sso: 'SSO 单点登录',
  graphql_support: 'GraphQL 支持',
  grpc_support: 'gRPC 支持',
  team_collaboration: '团队协作',
  api_key_management: 'API Key 管理',
  audit_log_export: '审计日志导出',
  custom_branding: '自定义品牌',
  sla_guarantee: 'SLA 保障',
  priority_support: '优先技术支持',
  dedicated_instance: '专属实例',
};

const QUOTA_LABELS: Record<string, string> = {
  max_schemas: '最大 Schema 数',
  max_scenarios_per_schema: '每 Schema 最大场景数',
  max_concurrent_executions: '最大并发执行数',
  max_team_members: '最大团队成员数',
  max_retention_days: '数据保留天数',
  distributed_workers: '分布式 Worker 数',
};

const PLAN_NAMES: Record<string, string> = {
  free: '社区版 (Free)',
  pro: '专业版 (Pro)',
  enterprise: '企业版 (Enterprise)',
};

const PLAN_PRICES: Record<string, string> = {
  free: '免费',
  pro: '¥299/月',
  enterprise: '联系我们',
};

const PLAN_COLORS: Record<string, string> = {
  free: 'bg-gray-100 border-gray-300',
  pro: 'bg-blue-50 border-blue-400',
  enterprise: 'bg-purple-50 border-purple-400',
};

const PLAN_BADGES: Record<string, string> = {
  free: '',
  pro: '🔥 最受欢迎',
  enterprise: '🏢 企业级',
};

export default function PricingPage() {
  const [plans, setPlans] = useState<Record<string, PlanFeatures> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/plans/compare')
      .then(r => r.json())
      .then(data => { setPlans(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  const planKeys = plans ? Object.keys(plans) : ['free', 'pro', 'enterprise'];
  const featureKeys = plans ? Object.keys(plans.free.features) : Object.keys(FEATURE_LABELS);

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold text-gray-900 mb-4">选择适合您的版本</h1>
        <p className="text-lg text-gray-600">
          从社区版到企业版，为不同规模的团队提供灵活的混沌工程解决方案
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-16">
        {planKeys.map(planKey => {
          const planData = plans?.[planKey];
          const quota = planData?.quota || {};
          return (
            <div
              key={planKey}
              className={`relative rounded-2xl border-2 p-8 ${PLAN_COLORS[planKey] || 'bg-white border-gray-200'} transition-transform hover:scale-105`}
            >
              {PLAN_BADGES[planKey] && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-blue-600 text-white text-xs font-bold px-3 py-1 rounded-full">
                  {PLAN_BADGES[planKey]}
                </div>
              )}
              <h2 className="text-2xl font-bold text-gray-900 mb-2">
                {PLAN_NAMES[planKey] || planKey}
              </h2>
              <div className="text-3xl font-extrabold text-gray-900 mb-6">
                {PLAN_PRICES[planKey] || '—'}
              </div>
              <ul className="space-y-3 mb-8">
                {QUOTA_LABELS && Object.entries(QUOTA_LABELS).map(([key, label]) => (
                  <li key={key} className="flex items-center text-sm text-gray-700">
                    <span className="mr-2 text-blue-500">📊</span>
                    <span className="font-medium">{label}:</span>
                    <span className="ml-1">{typeof quota[key] === 'boolean' ? (quota[key] ? '✓' : '✗') : (quota[key] ?? '—')}</span>
                  </li>
                ))}
              </ul>
              <button
                className={`w-full py-3 rounded-lg font-semibold transition-colors ${
                  planKey === 'pro'
                    ? 'bg-blue-600 text-white hover:bg-blue-700'
                    : planKey === 'enterprise'
                    ? 'bg-purple-600 text-white hover:bg-purple-700'
                    : 'bg-gray-800 text-white hover:bg-gray-900'
                }`}
              >
                {planKey === 'free' ? '开始使用' : planKey === 'enterprise' ? '联系销售' : '立即升级'}
              </button>
            </div>
          );
        })}
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
        <h2 className="text-2xl font-bold text-gray-900 p-6 border-b border-gray-200">
          功能对比详情
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50">
                <th className="text-left px-6 py-4 text-sm font-semibold text-gray-700">功能</th>
                {planKeys.map(pk => (
                  <th key={pk} className="text-center px-6 py-4 text-sm font-semibold text-gray-700">
                    {PLAN_NAMES[pk] || pk}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {featureKeys.map(fk => (
                <tr key={fk} className="border-t border-gray-100 hover:bg-gray-50">
                  <td className="px-6 py-4 text-sm text-gray-700">
                    {FEATURE_LABELS[fk] || fk}
                  </td>
                  {planKeys.map(pk => {
                    const available = plans?.[pk]?.features?.[fk];
                    return (
                      <td key={pk} className="text-center px-6 py-4">
                        {available ? (
                          <span className="text-green-500 text-lg">✓</span>
                        ) : (
                          <span className="text-gray-300 text-lg">✗</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
