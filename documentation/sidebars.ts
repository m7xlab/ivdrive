import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docsSidebar: [
    'intro',
    {
      type: 'category',
      label: 'Getting started',
      collapsed: false,
      items: [
        'getting-started/what-is-ivdrive',
        'getting-started/quick-start',
        'getting-started/create-account',
        'getting-started/add-vehicle',
      ],
    },
    {
      type: 'category',
      label: 'User guide',
      items: [
        'user-guide/dashboard',
        'user-guide/trips',
        'user-guide/charging',
        'user-guide/charging-curves',
        'user-guide/battery-health',
        'user-guide/statistics',
        'user-guide/settings',
        'user-guide/integrations-abrp',
        'user-guide/ai-coach',
      ],
    },
    {
      type: 'category',
      label: 'Self-hosting',
      items: [
        'self-hosting/overview',
        'self-hosting/docker-compose',
        'self-hosting/configuration',
        'self-hosting/landing-proxy',
        'self-hosting/upgrades',
      ],
    },
    {
      type: 'category',
      label: 'Reference',
      items: ['reference/architecture', 'reference/faq', 'reference/troubleshooting'],
    },
    {
      type: 'category',
      label: 'Community',
      items: [
        'community/contributing',
        'community/roadmap',
        'community/sponsors',
        'community/support',
      ],
    },
  ],
};

export default sidebars;
