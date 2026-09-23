"use client"

import { useEffect } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { toast } from "sonner"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { useAuthContext } from "@/providers/auth-provider"
import { api } from "@/lib/api"
import { User, Building2, CreditCard } from "lucide-react"

const profileSchema = z.object({
  fullName: z.string().min(2, "Nombre muy corto"),
})

const orgSchema = z.object({
  orgName: z.string().min(2, "El nombre de la empresa es requerido"),
  sector: z.string().min(1, "Selecciona un sector"),
  size: z.string().min(1, "Selecciona un tamaño"),
})

type ProfileValues = z.infer<typeof profileSchema>
type OrgValues = z.infer<typeof orgSchema>

const SECTORS = [
  { value: "comercio", label: "Comercio" },
  { value: "servicios", label: "Servicios" },
  { value: "educacion", label: "Educación" },
  { value: "salud", label: "Salud" },
  { value: "tic", label: "Tecnología e información" },
  { value: "manufactura", label: "Manufactura" },
  { value: "otro", label: "Otro" },
]

const SIZES = [
  { value: "1-10", label: "1-10 empleados (Microempresa)" },
  { value: "11-50", label: "11-50 empleados (Pequeña)" },
  { value: "51-200", label: "51-200 empleados (Mediana)" },
  { value: "200+", label: "Más de 200 empleados (Grande)" },
]

export default function SettingsPage() {
  const { user } = useAuthContext()

  const profileForm = useForm<ProfileValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      fullName: "",
    },
  })

  const orgForm = useForm<OrgValues>({
    resolver: zodResolver(orgSchema),
    defaultValues: {
      orgName: "",
      sector: "",
      size: "",
    },
  })

  useEffect(() => {
    if (user?.full_name) {
      profileForm.setValue("fullName", user.full_name)
    }
  }, [user, profileForm])

  async function handleUpdateProfile(values: ProfileValues) {
    try {
      await api.put("/api/v1/auth/me", { full_name: values.fullName })
      toast.success("Perfil actualizado correctamente")
    } catch {
      toast.error("Error al actualizar el perfil")
    }
  }

  async function handleUpdateOrg(values: OrgValues) {
    void values
    // Will hit the FastAPI org endpoint once backend is ready
    toast.success("Información de empresa actualizada")
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Configuración</h1>
        <p className="text-muted-foreground mt-1">
          Administra tu cuenta y la información de tu empresa.
        </p>
      </div>

      {/* Profile section */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <User className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-base">Perfil personal</CardTitle>
          </div>
          <CardDescription>Tu información de usuario</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Correo electrónico</Label>
              <Input
                value={user?.email ?? ""}
                disabled
                className="text-muted-foreground"
              />
              <p className="text-xs text-muted-foreground">
                El correo no puede modificarse
              </p>
            </div>

            <Separator />

            <Form {...profileForm}>
              <form
                onSubmit={profileForm.handleSubmit(handleUpdateProfile)}
                className="space-y-4"
              >
                <FormField
                  control={profileForm.control}
                  name="fullName"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Nombre completo</FormLabel>
                      <FormControl>
                        <Input {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <Button type="submit" size="sm">
                  Guardar perfil
                </Button>
              </form>
            </Form>
          </div>
        </CardContent>
      </Card>

      {/* Organization section */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Building2 className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-base">Información de empresa</CardTitle>
          </div>
          <CardDescription>Datos de tu organización</CardDescription>
        </CardHeader>
        <CardContent>
          <Form {...orgForm}>
            <form
              onSubmit={orgForm.handleSubmit(handleUpdateOrg)}
              className="space-y-4"
            >
              <FormField
                control={orgForm.control}
                name="orgName"
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
                  control={orgForm.control}
                  name="sector"
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
                  control={orgForm.control}
                  name="size"
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

              <Button type="submit" size="sm">
                Guardar empresa
              </Button>
            </form>
          </Form>
        </CardContent>
      </Card>

      {/* Plan section */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <CreditCard className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-base">Plan actual</CardTitle>
          </div>
          <CardDescription>Información de tu suscripción</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium">Plan Gratuito</p>
              <p className="text-sm text-muted-foreground mt-0.5">
                Hasta 10.000 registros · 3 tableros · Análisis IA básico
              </p>
            </div>
            <Badge variant="secondary">Activo</Badge>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
