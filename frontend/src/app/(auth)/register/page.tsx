"use client"

import Link from "next/link"
import { useState } from "react"
import { useForm, useWatch } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { ArrowRight, Check, ChevronLeft, Circle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { BusinessTypeSelector } from "@/components/auth/business-type-selector"
import { PasswordInput } from "@/components/kit/field"
import { Notice } from "@/components/kit/notice"
import { Steps } from "@/components/kit/steps"
import { useAuth } from "@/hooks/use-auth"
import { usePageTitle } from "@/hooks/use-page-title"
import { cn } from "@/lib/utils"

const registerSchema = z.object({
  full_name: z.string().trim().min(2, "Escribe tu nombre (al menos 2 letras)."),
  email: z.string().trim().min(1, "Escribe tu correo.").email("Revisa tu correo: parece que le falta algo (por ejemplo, la @)."),
  password: z
    .string()
    .min(8, "Usa al menos 8 caracteres.")
    .regex(/\d/, "Incluye al menos un número."),
  org_name: z.string().trim().min(2, "Escribe el nombre de tu empresa o negocio."),
  org_sector: z.enum(["terciario", "cuaternario", "TIC", "salud", "educacion", "comercio"], {
    error: "Elige el sector que más se parezca.",
  }),
  org_size: z.enum(["micro", "pequeña", "mediana"], {
    error: "Elige cuántas personas trabajan contigo.",
  }),
  business_type_id: z.string().min(1, "Elige el tipo de negocio que más se parezca al tuyo."),
})

type RegisterFormValues = z.infer<typeof registerSchema>

const SECTORS = [
  { value: "comercio", label: "Comercio" },
  { value: "terciario", label: "Servicios" },
  { value: "salud", label: "Salud" },
  { value: "educacion", label: "Educación" },
  { value: "TIC", label: "Tecnología e informática" },
  { value: "cuaternario", label: "Conocimiento (educación, salud o TIC)" },
] as const

const SIZES = [
  { value: "micro", label: "De 1 a 10 personas" },
  { value: "pequeña", label: "De 11 a 50 personas" },
  { value: "mediana", label: "De 51 a 200 personas" },
] as const

const STEPS = [
  { id: "account", label: "Tu cuenta" },
  { id: "business", label: "Tu negocio" },
  { id: "confirm", label: "Confirmar" },
]

const STEP_FIELDS: Record<number, (keyof RegisterFormValues)[]> = {
  0: ["full_name", "email", "password"],
  1: ["org_name", "org_sector", "org_size", "business_type_id"],
}

function PasswordHints({ value }: { value: string }) {
  const rules = [
    { ok: value.length >= 8, text: "8 caracteres o más" },
    { ok: /\d/.test(value), text: "Al menos un número" },
  ]
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[13px]" aria-label="Requisitos de la contraseña">
      {rules.map((r) => (
        <li key={r.text} className={cn("inline-flex items-center gap-1.5", r.ok ? "text-success-strong" : "text-muted-foreground")}>
          {r.ok ? <Check className="h-3.5 w-3.5" aria-hidden="true" /> : <Circle className="h-3 w-3" aria-hidden="true" />}
          {r.text}
          <span className="sr-only">{r.ok ? "(cumplido)" : "(pendiente)"}</span>
        </li>
      ))}
    </ul>
  )
}

export default function RegisterPage() {
  usePageTitle("Crear cuenta")
  const { signUp, loading, errorInfo, clearError } = useAuth()
  const [step, setStep] = useState(0)

  const form = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      full_name: "",
      email: "",
      password: "",
      org_name: "",
      org_sector: undefined,
      org_size: undefined,
      business_type_id: "",
    },
  })
  const password = useWatch({ control: form.control, name: "password" }) ?? ""

  async function next() {
    const valid = await form.trigger(STEP_FIELDS[step])
    if (valid) setStep((s) => s + 1)
  }

  async function onSubmit(values: RegisterFormValues) {
    await signUp({ ...values, full_name: values.full_name.trim(), email: values.email.trim(), org_name: values.org_name.trim() })
  }

  const v = form.getValues()

  return (
    <div className="space-y-7">
      <div className="space-y-2">
        <h1 className="font-display text-[34px] font-semibold leading-tight">Crea tu cuenta</h1>
        <p className="text-[15px] text-muted-foreground">Tres pasos cortos y empiezas a entender tus números.</p>
      </div>

      <Steps steps={STEPS} current={step} />

      {errorInfo && (
        <Notice
          tone="danger"
          title={errorInfo.title}
          onDismiss={clearError}
          action={
            errorInfo.action === "login" ? (
              <Button asChild size="sm" variant="outline">
                <Link href="/login">Iniciar sesión</Link>
              </Button>
            ) : undefined
          }
        >
          {errorInfo.description}
        </Notice>
      )}

      <Form {...form}>
        <form
          onSubmit={(e) => {
            if (step < 2) {
              e.preventDefault()
              void next()
              return
            }
            void form.handleSubmit(onSubmit)(e)
          }}
          className="space-y-5"
          noValidate
        >
          {step === 0 && (
            <>
              <FormField
                control={form.control}
                name="full_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Tu nombre</FormLabel>
                    <FormControl>
                      <Input placeholder="Ej.: Ana Pérez" autoComplete="name" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Correo electrónico</FormLabel>
                    <FormControl>
                      <Input placeholder="ana@minegocio.com" type="email" autoComplete="email" inputMode="email" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Contraseña</FormLabel>
                    <FormControl>
                      <PasswordInput placeholder="Mínimo 8 caracteres" autoComplete="new-password" {...field} />
                    </FormControl>
                    <PasswordHints value={password} />
                    <FormMessage />
                  </FormItem>
                )}
              />
            </>
          )}

          {step === 1 && (
            <>
              <FormField
                control={form.control}
                name="org_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Nombre de tu empresa o negocio</FormLabel>
                    <FormControl>
                      <Input placeholder="Ej.: Café El Faro" autoComplete="organization" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <div className="grid gap-5 sm:grid-cols-2">
                <FormField
                  control={form.control}
                  name="org_sector"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Sector</FormLabel>
                      <Select onValueChange={field.onChange} defaultValue={field.value}>
                        <FormControl>
                          <SelectTrigger className="w-full">
                            <SelectValue placeholder="Elige uno" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {SECTORS.map((s) => (
                            <SelectItem key={s.value} value={s.value}>
                              {s.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="org_size"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>¿Cuántas personas son?</FormLabel>
                      <Select onValueChange={field.onChange} defaultValue={field.value}>
                        <FormControl>
                          <SelectTrigger className="w-full">
                            <SelectValue placeholder="Elige uno" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {SIZES.map((s) => (
                            <SelectItem key={s.value} value={s.value}>
                              {s.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
              <FormField
                control={form.control}
                name="business_type_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>¿A qué se parece más tu negocio?</FormLabel>
                    <p className="text-[13px] text-muted-foreground">Así te preparamos hojas listas para llenar. Podrás subir cualquier archivo igual.</p>
                    <FormControl>
                      <BusinessTypeSelector value={field.value} onChange={field.onChange} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </>
          )}

          {step === 2 && (
            <div className="space-y-3">
              <p className="text-sm font-semibold">Revisa que todo esté bien</p>
              <dl className="divide-y rounded-2xl border bg-card text-sm">
                {[
                  ["Nombre", v.full_name],
                  ["Correo", v.email],
                  ["Empresa", v.org_name],
                  ["Sector", SECTORS.find((s) => s.value === v.org_sector)?.label ?? "—"],
                  ["Tamaño", SIZES.find((s) => s.value === v.org_size)?.label ?? "—"],
                ].map(([k, val]) => (
                  <div key={k} className="flex justify-between gap-4 px-4 py-3">
                    <dt className="text-muted-foreground">{k}</dt>
                    <dd className="truncate text-right font-medium">{val}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}

          <div className="flex flex-col-reverse gap-2 pt-1 sm:flex-row">
            {step > 0 && (
              <Button type="button" variant="outline" size="lg" className="sm:flex-1" onClick={() => setStep((s) => s - 1)} disabled={loading}>
                <ChevronLeft aria-hidden="true" />
                Atrás
              </Button>
            )}
            <Button type="submit" size="lg" className="sm:flex-1" loading={loading} loadingText="Creando tu cuenta…">
              {step < 2 ? "Continuar" : "Crear cuenta"}
              <ArrowRight aria-hidden="true" />
            </Button>
          </div>
        </form>
      </Form>

      <p className="text-center text-sm text-muted-foreground">
        ¿Ya tienes cuenta?{" "}
        <Link href="/login" className="font-semibold text-primary underline-offset-4 hover:underline">
          Inicia sesión
        </Link>
      </p>
    </div>
  )
}
