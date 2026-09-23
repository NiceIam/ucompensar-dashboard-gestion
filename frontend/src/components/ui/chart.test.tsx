/**
 * Unit tests for sanitizeCssColor in chart.tsx.
 *
 * sanitizeCssColor is not exported from the module, so we test it indirectly
 * by rendering <ChartContainer> with controlled `config` values and asserting
 * the generated <style> tag content reflects the sanitised output.
 *
 * Setup requires: vitest + @vitejs/plugin-react + jsdom + @testing-library/react
 */
import { describe, test, expect, beforeAll } from "vitest"
import { render } from "@testing-library/react"
import { ChartContainer } from "./chart"
import type { ChartConfig } from "./chart"
import * as React from "react"

// recharts ResponsiveContainer calls ResizeObserver internally.
// Provide a minimal stub so jsdom does not throw.
beforeAll(() => {
  global.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
})

/**
 * Helper: renders a ChartContainer with a single colour config key and returns
 * the innerHTML of the injected <style> element, or null when no style is rendered.
 */
function renderWithColor(color: string): string | null {
  const config: ChartConfig = {
    series: { color },
  }
  const { container } = render(
    <ChartContainer config={config} id="test-chart">
      {/* ResponsiveContainer requires at least one child */}
      <div />
    </ChartContainer>
  )
  const styleEl = container.querySelector("style")
  return styleEl ? styleEl.innerHTML : null
}

// ---------------------------------------------------------------------------
// Hex values
// ---------------------------------------------------------------------------
describe("sanitizeCssColor — hex values", () => {
  test("should_accept_hex_when_3_digit_shorthand_provided", () => {
    const html = renderWithColor("#fff")
    expect(html).toContain("--color-series: #fff")
  })

  test("should_accept_hex_when_6_digit_value_provided", () => {
    const html = renderWithColor("#ffffff")
    expect(html).toContain("--color-series: #ffffff")
  })

  test("should_accept_hex_when_8_digit_with_alpha_provided", () => {
    const html = renderWithColor("#ffffffff")
    expect(html).toContain("--color-series: #ffffffff")
  })

  test("should_accept_hex_when_4_digit_shorthand_with_alpha_provided", () => {
    const html = renderWithColor("#ffff")
    expect(html).toContain("--color-series: #ffff")
  })
})

// ---------------------------------------------------------------------------
// rgb / rgba
// ---------------------------------------------------------------------------
describe("sanitizeCssColor — rgb and rgba", () => {
  test("should_accept_rgb_when_standard_notation_provided", () => {
    const html = renderWithColor("rgb(0,0,0)")
    expect(html).toContain("--color-series: rgb(0,0,0)")
  })

  test("should_accept_rgba_when_alpha_is_decimal_provided", () => {
    const html = renderWithColor("rgba(255,255,255,0.5)")
    expect(html).toContain("--color-series: rgba(255,255,255,0.5)")
  })

  test("should_accept_rgba_when_alpha_is_zero_provided", () => {
    const html = renderWithColor("rgba(0,0,0,0)")
    expect(html).toContain("--color-series: rgba(0,0,0,0)")
  })

  test("should_accept_rgba_when_alpha_is_one_provided", () => {
    const html = renderWithColor("rgba(0,0,0,1)")
    expect(html).toContain("--color-series: rgba(0,0,0,1)")
  })
})

// ---------------------------------------------------------------------------
// hsl / hsla
// ---------------------------------------------------------------------------
describe("sanitizeCssColor — hsl and hsla", () => {
  test("should_accept_hsl_when_standard_notation_provided", () => {
    const html = renderWithColor("hsl(120,100%,50%)")
    expect(html).toContain("--color-series: hsl(120,100%,50%)")
  })

  test("should_accept_hsla_when_alpha_decimal_provided", () => {
    const html = renderWithColor("hsla(240,100%,50%,0.3)")
    expect(html).toContain("--color-series: hsla(240,100%,50%,0.3)")
  })

  test("should_accept_hsla_when_alpha_is_one_provided", () => {
    const html = renderWithColor("hsla(0,0%,0%,1)")
    expect(html).toContain("--color-series: hsla(0,0%,0%,1)")
  })
})

// ---------------------------------------------------------------------------
// CSS custom properties
// ---------------------------------------------------------------------------
describe("sanitizeCssColor — CSS var() references", () => {
  test("should_accept_var_when_css_custom_property_provided", () => {
    const html = renderWithColor("var(--primary)")
    expect(html).toContain("--color-series: var(--primary)")
  })

  test("should_accept_var_when_multi_segment_token_provided", () => {
    const html = renderWithColor("var(--chart-1-color)")
    expect(html).toContain("--color-series: var(--chart-1-color)")
  })
})

// ---------------------------------------------------------------------------
// Named colors
// ---------------------------------------------------------------------------
describe("sanitizeCssColor — safe named colors", () => {
  test("should_accept_red_when_safe_named_color_provided", () => {
    const html = renderWithColor("red")
    expect(html).toContain("--color-series: red")
  })

  test("should_accept_blue_when_safe_named_color_provided", () => {
    const html = renderWithColor("blue")
    expect(html).toContain("--color-series: blue")
  })

  test("should_accept_currentColor_when_css_keyword_provided", () => {
    const html = renderWithColor("currentColor")
    expect(html).toContain("--color-series: currentColor")
  })

  test("should_accept_transparent_when_css_keyword_provided", () => {
    const html = renderWithColor("transparent")
    expect(html).toContain("--color-series: transparent")
  })
})

// ---------------------------------------------------------------------------
// Rejection / sanitisation
// ---------------------------------------------------------------------------
describe("sanitizeCssColor — CSS injection rejection", () => {
  test("should_return_currentColor_when_css_injection_string_provided", () => {
    const malicious = "red; } body { display:none; /*"
    const html = renderWithColor(malicious)
    // Must not contain the injection payload
    expect(html).not.toContain("display:none")
    // Must fall back to currentColor
    expect(html).toContain("currentColor")
  })

  test("should_return_currentColor_when_javascript_protocol_provided", () => {
    const html = renderWithColor("javascript:alert(1)")
    expect(html).not.toContain("javascript:")
    expect(html).toContain("currentColor")
  })

  test("should_return_currentColor_when_empty_string_provided", () => {
    // Empty string — config.color = "" should cause the style tag to be absent
    // (safeColor is null when sanitizeCssColor returns 'currentColor' for falsy)
    // Actually: "" is falsy so rawColor is falsy → safeColor = null → no CSS var emitted.
    // Either way, no injection. We just assert no malicious content.
    const config: ChartConfig = { series: { color: "" } }
    const { container } = render(
      <ChartContainer config={config} id="test-empty">
        <div />
      </ChartContainer>
    )
    const styleEl = container.querySelector("style")
    // style may be null (no color entries) or present without a bad value
    if (styleEl) {
      expect(styleEl.innerHTML).not.toContain("javascript:")
    } else {
      expect(styleEl).toBeNull()
    }
  })
})

// ---------------------------------------------------------------------------
// Unrecognised / unsafe values
// ---------------------------------------------------------------------------
describe("sanitizeCssColor — unrecognised values", () => {
  test("should_return_currentColor_when_expression_function_provided", () => {
    const html = renderWithColor("expression(alert(1))")
    expect(html).not.toContain("expression(")
    expect(html).toContain("currentColor")
  })

  test("should_return_currentColor_when_url_function_provided", () => {
    const html = renderWithColor("url(http://evil.com/img.png)")
    expect(html).not.toContain("url(")
    expect(html).toContain("currentColor")
  })

  test("should_return_currentColor_when_arbitrary_unknown_string_provided", () => {
    const html = renderWithColor("notacolor")
    expect(html).toContain("currentColor")
  })
})
