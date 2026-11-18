<script>
  import * as echarts from 'echarts/core';
  import { LineChart, BarChart, ScatterChart, PieChart } from 'echarts/charts';
  import { GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, GraphicComponent } from 'echarts/components';
  import { SVGRenderer } from 'echarts/renderers';

  echarts.use([LineChart, BarChart, ScatterChart, PieChart, GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, GraphicComponent, SVGRenderer]);

  /** option: function returning an ECharts option (called again when the colour scheme or size changes).
      It receives { width, height, chart } for drawings that need pixel positions. */
  let { option, height = 280, onclick = null, label = 'Chart' } = $props();

  let el;
  let chart;
  let scheme = $state(matchMedia('(prefers-color-scheme: dark)').matches);
  let size = $state({ width: 0, height: 0 });

  $effect(() => {
    const mq = matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => (scheme = mq.matches);
    mq.addEventListener('change', onChange);
    chart = echarts.init(el, null, { renderer: 'svg' });
    size = { width: el.clientWidth, height: el.clientHeight };
    const ro = new ResizeObserver(() => {
      chart?.resize();
      if (el.clientWidth !== size.width || el.clientHeight !== size.height) size = { width: el.clientWidth, height: el.clientHeight };
    });
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
    const opt = option({ ...size, chart });
    if (chart && opt) chart.setOption(opt, true);
  });

  $effect(() => {
    if (!chart) return;
    chart.off('click');
    if (onclick) chart.on('click', (p) => onclick(p));
  });
</script>

<div bind:this={el} style="height: {height}px; width: 100%;" role="img" aria-label={label}></div>
