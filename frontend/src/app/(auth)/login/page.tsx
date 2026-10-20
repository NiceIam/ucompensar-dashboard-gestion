"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { useEffect } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { ArrowRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form"
import { PasswordInput } from "@/components/kit/field"
import { Notice } from "@/components/kit/notice"
import { useAuth } from "@/hooks/use-auth"
import { usePageTitle } from "@/hooks/use-page-title"
import { useAuthContext } from "@/providers/auth-provider"

const loginSchema = z.object({
  email: z.string().trim().min(1, "Escribe tu correo.").email("Revisa tu correo: parece que le falta algo (por ejemplo, la @)."),
  password: z.string().min(1, "Escribe tu contraseña."),
})

type LoginFormValues = z.infer<typeof loginSchema>

export default function LoginPage() {
  usePageTitle("Ingresar")
  const { signIn, loading, errorInfo, clearError } = useAuth()

  // Quien ya tiene una sesion VALIDA (segun /auth/me) no necesita ver el login. Una cookie vieja o invalida no
  // cuenta: /auth/me responde 401, no hay usuario y el formulario se muestra normalmente.
  const { user, loading: sessionLoading } = useAuthContext()
  const router = useRouter()
  useEffect(() => {
    if (!sessionLoading && user) router.replace("/")
  }, [sessionLoading, user, router])

  const form = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  })

  async function onSubmit(values: LoginFormValues) {
    await signIn(values.email.trim(), values.password)
  }

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="font-display text-[34px] font-semibold leading-tight">Qué bueno verte</h1>
        <p className="text-[15px] text-muted-foreground">Entra para ver cómo va tu negocio y preguntarle a tus datos.</p>
      </div>

      {errorInfo && (
        <Notice tone="danger" title={errorInfo.title} onDismiss={clearError}>
          {errorInfo.description}
        </Notice>
      )}

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-5" noValidate>
          <FormField
            control={form.control}
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Correo electrónico</FormLabel>
                <FormControl>
                  <Input placeholder="empresa@ejemplo.com" type="email" autoComplete="email" inputMode="email" {...field} />
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
                  <PasswordInput placeholder="••••••••" autoComplete="current-password" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <Button type="submit" size="lg" className="w-full" loading={loading} loadingText="Ingresando…">
            Ingresar
            <ArrowRight aria-hidden="true" />
          </Button>
        </form>
      </Form>

      <p className="text-center text-sm text-muted-foreground">
        ¿Aún no tienes cuenta?{" "}
        <Link href="/register" className="font-semibold text-primary underline-offset-4 hover:underline">
          Regístrate aquí
        </Link>
      </p>
    </div>
  )
}
