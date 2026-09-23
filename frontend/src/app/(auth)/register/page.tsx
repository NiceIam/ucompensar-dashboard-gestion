"use client"

import Link from "next/link"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Alert } from "@/components/ui/alert"
import { BusinessTypeSelector } from "@/components/auth/business-type-selector"
import { useAuth } from "@/hooks/use-auth"
import { ChevronLeft } from "lucide-react"
import Image from "next/image"
import { cn } from "@/lib/utils"

const registerSchema = z.object({
  full_name: z.string().min(2, "Nombre muy corto"),
  email: z.string().email("Correo electrónico inválido"),
  password: z
    .string()
    .min(8, "La contraseña debe tener al menos 8 caracteres")
    .regex(/\d/, "Debe contener al menos un número"),
  org_name: z.string().min(2, "El nombre de la empresa es requerido"),
  org_sector: z.enum(
    ["terciario", "cuaternario", "TIC", "salud", "educacion", "comercio"],
    { error: "Selecciona un sector válido" },
  ),
  org_size: z.enum(["micro", "pequeña", "mediana"], {
    error: "Selecciona el tamaño de tu empresa",
  }),
  business_type_id: z.string().min(1, "Selecciona el tipo de negocio"),
})

type RegisterFormValues = z.infer<typeof registerSchema>

const SECTORS = [
  { value: "terciario", label: "Servicios" },
  { value: "cuaternario", label: "Educación / Salud / TIC" },
  { value: "TIC", label: "Tecnología e Informática" },
  { value: "salud", label: "Salud" },
  { value: "educacion", label: "Educación" },
  { value: "comercio", label: "Comercio" },
] as const

const SIZES = [
  { value: "micro", label: "Micro (1-10 empleados)" },
  { value: "pequeña", label: "Pequeña (11-50 empleados)" },
  { value: "mediana", label: "Mediana (51-200 empleados)" },
] as const

const STEPS = [
  { number: 1, label: "Cuenta" },
  { number: 2, label: "Tipo de negocio" },
  { number: 3, label: "Confirmar" },
]

// Fields validated per step
const STEP_FIELDS: Record<number, (keyof RegisterFormValues)[]> = {
  1: ["full_name", "email", "password", "org_name", "org_sector", "org_size"],
  2: ["business_type_id"],
}

export default function RegisterPage() {
  const { signUp, loading, error } = useAuth()
  const [currentStep, setCurrentStep] = useState(1)

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

  async function goToNextStep() {
    const fields = STEP_FIELDS[currentStep]
    const valid = await form.trigger(fields)
    if (valid) {
      setCurrentStep((s) => s + 1)
    }
  }

  async function onSubmit(values: RegisterFormValues) {
    await signUp(values)
  }

  return (
    <Card className="shadow-lg">
      <CardHeader className="space-y-4 text-center">
        <div className="flex justify-center">
          <Image
            src="/logo-ucompensar.png"
            alt="Compensar Fundación Universitaria"
            width={200}
            height={50}
            className="h-10 w-auto"
            priority
          />
        </div>
        <div>
          <CardTitle className="text-2xl">Crear cuenta</CardTitle>
          <CardDescription className="mt-1">
            Comienza a gestionar los datos de tu empresa con IA
          </CardDescription>
        </div>

        {/* Step indicator */}
        <div className="flex items-center justify-center gap-0 pt-1">
          {STEPS.map((step, index) => (
            <div key={step.number} className="flex items-center">
              {/* Step circle */}
              <div className="flex flex-col items-center gap-1">
                <span
                  className={cn(
                    "flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold transition-colors",
                    currentStep === step.number
                      ? "bg-primary text-primary-foreground"
                      : currentStep > step.number
                        ? "bg-primary/20 text-primary"
                        : "bg-muted text-muted-foreground",
                  )}
                >
                  {currentStep > step.number ? "✓" : step.number}
                </span>
                <span
                  className={cn(
                    "hidden text-[10px] font-medium sm:block",
                    currentStep >= step.number
                      ? "text-primary"
                      : "text-muted-foreground",
                  )}
                >
                  {step.label}
                </span>
              </div>

              {/* Connector line */}
              {index < STEPS.length - 1 && (
                <div
                  className={cn(
                    "mx-2 mb-4 h-px w-10 transition-colors sm:w-14",
                    currentStep > step.number
                      ? "bg-primary/40"
                      : "bg-border",
                  )}
                />
              )}
            </div>
          ))}
        </div>
      </CardHeader>

      <CardContent>
        {error && (
          <Alert className="mb-4 border-destructive/50 text-destructive">
            {error}
          </Alert>
        )}

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            {/* Step 1: Personal & company data */}
            {currentStep === 1 && (
              <>
                <FormField
                  control={form.control}
                  name="full_name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Nombre completo</FormLabel>
                      <FormControl>
                        <Input placeholder="Juan Pérez" {...field} />
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
                        <Input
                          placeholder="juan@miempresa.com"
                          type="email"
                          {...field}
                        />
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
                        <Input
                          placeholder="Mínimo 8 caracteres"
                          type="password"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="org_name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Nombre de la empresa</FormLabel>
                      <FormControl>
                        <Input placeholder="Mi Empresa S.A.S." {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className="grid grid-cols-2 gap-4">
                  <FormField
                    control={form.control}
                    name="org_sector"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Sector</FormLabel>
                        <Select
                          onValueChange={field.onChange}
                          defaultValue={field.value}
                        >
                          <FormControl>
                            <SelectTrigger className="w-full">
                              <SelectValue placeholder="Seleccionar" />
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
                        <FormLabel>Tamaño</FormLabel>
                        <Select
                          onValueChange={field.onChange}
                          defaultValue={field.value}
                        >
                          <FormControl>
                            <SelectTrigger className="w-full">
                              <SelectValue placeholder="Seleccionar" />
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

                <Button
                  type="button"
                  className="w-full"
                  onClick={goToNextStep}
                >
                  Continuar
                </Button>
              </>
            )}

            {/* Step 2: Business type selection */}
            {currentStep === 2 && (
              <>
                <div className="space-y-1.5">
                  <p className="text-sm font-medium leading-none">
                    ¿Cuál es el tipo de negocio de tu empresa?
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Usaremos esto para crear las tablas y dashboards correctos automáticamente.
                  </p>
                </div>

                <FormField
                  control={form.control}
                  name="business_type_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormControl>
                        <BusinessTypeSelector
                          value={field.value}
                          onChange={field.onChange}
                          error={form.formState.errors.business_type_id?.message}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className="flex gap-3 pt-1">
                  <Button
                    type="button"
                    variant="outline"
                    className="flex-1 gap-1.5"
                    onClick={() => setCurrentStep(1)}
                  >
                    <ChevronLeft className="h-4 w-4" />
                    Atrás
                  </Button>
                  <Button
                    type="button"
                    className="flex-1"
                    onClick={goToNextStep}
                  >
                    Continuar
                  </Button>
                </div>
              </>
            )}

            {/* Step 3: Confirmation */}
            {currentStep === 3 && (
              <>
                <div className="space-y-1.5">
                  <p className="text-sm font-medium leading-none">
                    Confirma tus datos
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Revisa la información antes de crear tu cuenta.
                  </p>
                </div>

                <div className="rounded-lg border bg-muted/30 p-4 space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Nombre</span>
                    <span className="font-medium">{form.getValues("full_name")}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Correo</span>
                    <span className="font-medium">{form.getValues("email")}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Empresa</span>
                    <span className="font-medium">{form.getValues("org_name")}</span>
                  </div>
                </div>

                <div className="flex gap-3">
                  <Button
                    type="button"
                    variant="outline"
                    className="flex-1 gap-1.5"
                    onClick={() => setCurrentStep(2)}
                    disabled={loading}
                  >
                    <ChevronLeft className="h-4 w-4" />
                    Atrás
                  </Button>
                  <Button
                    type="submit"
                    className="flex-1"
                    disabled={loading}
                  >
                    {loading ? "Creando cuenta..." : "Crear cuenta"}
                  </Button>
                </div>
              </>
            )}
          </form>
        </Form>
      </CardContent>

      <CardFooter className="justify-center text-sm text-muted-foreground">
        ¿Ya tienes cuenta?&nbsp;
        <Link href="/login" className="text-primary hover:underline font-medium">
          Inicia sesión
        </Link>
      </CardFooter>
    </Card>
  )
}
