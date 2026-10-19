import { describe, expect, test } from "vitest"
import { render, screen } from "@testing-library/react"
import { useForm } from "react-hook-form"
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "./form"
import { Input } from "./input"

function Demo({ withError = false }: { withError?: boolean }) {
  const form = useForm<{ email: string }>({ defaultValues: { email: "" } })
  if (withError && !form.formState.errors.email) form.setError("email", { message: "Revisa tu correo." })
  return (
    <Form {...form}>
      <form>
        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Correo electrónico</FormLabel>
              <FormControl>
                <Input {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </form>
    </Form>
  )
}

describe("FormControl", () => {
  // Antes el id iba a un <div> envolvente: la etiqueta no quedaba asociada al campo.
  test("la etiqueta queda asociada al campo real", () => {
    render(<Demo />)
    const input = screen.getByLabelText("Correo electrónico")
    expect(input.tagName).toBe("INPUT")
    expect(input).toHaveAttribute("aria-invalid", "false")
  })

  test("el error se marca en el campo y se describe con el mensaje", () => {
    render(<Demo withError />)
    const input = screen.getByLabelText("Correo electrónico")
    expect(input).toHaveAttribute("aria-invalid", "true")
    const message = screen.getByText("Revisa tu correo.")
    expect(input.getAttribute("aria-describedby")).toContain(message.id)
  })
})
