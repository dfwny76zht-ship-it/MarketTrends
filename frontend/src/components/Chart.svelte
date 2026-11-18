<script>
  import * as echarts from 'echarts/core';
  import { LineChart, BarChart, ScatterChart } from 'echarts/charts';
  import { GridComponent, TooltipComponent, LegendComponent, MarkLineComponent } from 'echarts/components';
  import { SVGRenderer } from 'echarts/renderers';

  echarts.use([LineChart, BarChart, ScatterChart, GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, SVGRenderer]);

  /** option: function returning an ECharts option (called again when the colour scheme changes). */
  let { option, height = 280, onclick = null, label = 'Chart' } = $props();

  let el;
  let chart;
  let scheme = $state(matchMedia('(prefers-color-scheme: dark)').matches);

  $effect(() => {
    const mq = matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => (scheme = mq.matches);
    mq.addEventListener('change', onChange);
    chart = echarts.init(el, null, { renderer: 'svg' });
    const ro = new ResizeObserver(() => chart?.resize());
    ro.observe(el);
    return () => {
      mq.removeEventListener('change', onChange);
      ro.disconnect();
      chart?.dispose();
      chart = null;
    };
  });

  $effect(() => {
    scheme;
    const opt = option();
    if (chart && opt) chart.setOption(opt, true);
  });

  $effect(() => {
    if (!chart) return;
    chart.off('click');
    if (onclick) chart.on('click', (p) => onclick(p));
  });
</script>

<div bind:this={el} style="height: {height}px; width: 100%;" role="img" aria-label={label}></div>
