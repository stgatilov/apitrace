##########################################################################
#
# Copyright 2010 VMware, Inc.
# All Rights Reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
##########################################################################/


import stdapi
import glapi
from retrace import Retracer


class GlRetracer(Retracer):

    def retrace_function(self, function):
        Retracer.retrace_function(self, function)

    def call_function(self, function):
        if function.name in ("glDrawArrays", "glDrawElements", "glDrawRangeElements", "glMultiDrawElements"):
            print '    GLint __array_buffer = 0;'
            print '    glGetIntegerv(GL_ARRAY_BUFFER_BINDING, &__array_buffer);'
            print '    if (!__array_buffer) {'
            self.fail_function(function)
            print '    }'

        if function.name == "glViewport":
            print '    if (x + width > __window_width) {'
            print '        __window_width = x + width;'
            print '        __reshape_window = true;'
            print '    }'
            print '    if (y + height > __window_height) {'
            print '        __window_height = y + height;'
            print '        __reshape_window = true;'
            print '    }'

        if function.name == "glEnd":
            print '    insideGlBeginEnd = false;'
        
        Retracer.call_function(self, function)

        if function.name == "glBegin":
            print '    insideGlBeginEnd = true;'
        else:
            # glGetError is not allowed inside glBegin/glEnd
            print '    checkGlError();'


    def extract_arg(self, function, arg, arg_type, lvalue, rvalue):
        if function.name in [
            "glColorPointer",
            "glEdgeFlagPointer",
            "glIndexPointer",
            "glNormalPointer",
            "glTexCoordPointer",
            "glVertexPointer",
            "glFogCoordPointer",
            "glSecondaryColorPointer",
            "glVertexAttribPointer",
        ] and arg.name == 'pointer':
            self.extract_pointer(function, arg, arg_type, lvalue, rvalue)
        else:
            Retracer.extract_arg(self, function, arg, arg_type, lvalue, rvalue)

    def extract_pointer(self, function, arg, arg_type, lvalue, rvalue):
        print '    if (dynamic_cast<Trace::Null *>(&%s)) {' % rvalue
        print '        %s = 0;' % (lvalue)
        print '    } else {'
        print '        %s = (%s)(uintptr_t)(%s);' % (lvalue, arg_type, rvalue)
        print '    }'


if __name__ == '__main__':
    print '''
#include <string.h>
#include <iostream>

#include "glproc.hpp"
#include <GL/glut.h>

static bool double_buffer = false;
static bool insideGlBeginEnd = false;

static int __window_width = 256, __window_height = 256;
bool __reshape_window = false;

unsigned __frame = 0;
long long __startTime = 0;

static void
checkGlError(void) {
    if (insideGlBeginEnd) {
        return;
    }

    GLenum error = glGetError();
    if (error == GL_NO_ERROR) {
        return;
    }

    std::cerr << "warning: glGetError() = ";
    switch (error) {
    case GL_INVALID_ENUM:
        std::cerr << "GL_INVALID_ENUM";
        break;
    case GL_INVALID_VALUE:
        std::cerr << "GL_INVALID_VALUE";
        break;
    case GL_INVALID_OPERATION:
        std::cerr << "GL_INVALID_OPERATION";
        break;
    case GL_STACK_OVERFLOW:
        std::cerr << "GL_STACK_OVERFLOW";
        break;
    case GL_STACK_UNDERFLOW:
        std::cerr << "GL_STACK_UNDERFLOW";
        break;
    case GL_OUT_OF_MEMORY:
        std::cerr << "GL_OUT_OF_MEMORY";
        break;
    case GL_INVALID_FRAMEBUFFER_OPERATION:
        std::cerr << "GL_INVALID_FRAMEBUFFER_OPERATION";
        break;
    case GL_TABLE_TOO_LARGE:
        std::cerr << "GL_TABLE_TOO_LARGE";
        break;
    default:
        std::cerr << error;
        break;
    }
    std::cerr << "\\n";
}
'''
    api = glapi.glapi
    retracer = GlRetracer()
    retracer.retrace_api(glapi.glapi)
    print '''

static Trace::Parser parser;

static void display_noop(void) {
}

static void display(void) {
    Trace::Call *call;

    while ((call = parser.parse_call())) {
        if (call->name() == "glFlush") {
            glFlush();
            if (!double_buffer) {
                ++__frame;
                return;
            }
        }
        
        if (!retrace_call(*call)) {
            if (call->name() == "glXSwapBuffers" ||
                call->name() == "wglSwapBuffers") {
                if (double_buffer)
                    glutSwapBuffers();
                else
                    glFlush();
                ++__frame;
                return;
            }
        }
    }

    // Reached the end of trace
    glFlush();

    long long endTime = OS::GetTime();
    float timeInterval = (endTime - __startTime) * 1.0E-6;

    std::cout << 
        "Rendered " << __frame << " frames"
        " in " <<  timeInterval << " secs,"
        " average of " << (__frame/timeInterval) << " fps\\n";

    glutDisplayFunc(&display_noop);
    glutIdleFunc(NULL);
}

static void idle(void) {
    if (__reshape_window) {
        // XXX: doesn't quite work
        glutReshapeWindow(__window_width, __window_height);
        __reshape_window = false;
    }
    glutPostRedisplay();
}

int main(int argc, char **argv)
{

    int i;
    for (i = 1; i < argc; ++i) {
        const char *arg = argv[i];

        if (arg[0] != '-') {
            break;
        }

        if (!strcmp(arg, "--")) {
            break;
        }
        else if (!strcmp(arg, "-db")) {
            double_buffer = true;
        } else if (!strcmp(arg, "-v")) {
            ++verbosity;
        } else {
            std::cerr << "error: unknown option " << arg << "\\n";
            return 1;
        }
    }

    glutInit(&argc, argv);
    glutInitWindowPosition(0, 0);
    glutInitWindowSize(__window_width, __window_height);
    glutInitDisplayMode(GLUT_DEPTH | GLUT_RGB | (double_buffer ? GLUT_DOUBLE : GLUT_SINGLE));
    glutCreateWindow(argv[0]);

    glutDisplayFunc(&display);
    glutIdleFunc(&idle);

    for (GLuint h = 0; h < 1024; ++h) {
        __list_map[h] = h;
    }

    for ( ; i < argc; ++i) {
        if (parser.open(argv[i])) {
            __startTime = OS::GetTime();
            glutMainLoop();
            parser.close();
        }
    }

    return 0;
}

'''    
